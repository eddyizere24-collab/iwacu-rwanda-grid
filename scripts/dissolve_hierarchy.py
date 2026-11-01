#!/usr/bin/env python3
"""Dissolve NISR village polygons into cell/sector/district/province/country.

Snap tolerance: 1.0 metre in UTM EPSG:32736 before union (closes slivers).
CHANGED 2026-11-01 GROK: artifact-only; see docs/HANDOFF.md
"""
from __future__ import annotations
import argparse, json, gzip, hashlib, collections, math
from pathlib import Path
from datetime import datetime, timezone
from shapely.geometry import shape, mapping, Point
from shapely.ops import unary_union, transform, snap
from shapely.validation import make_valid
from pyproj import Transformer

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32736", always_xy=True)
TO_WGS = Transformer.from_crs("EPSG:32736", "EPSG:4326", always_xy=True)
SNAP_M = 1.0  # stated snap tolerance

def to_utm(g):
    return transform(lambda x, y: TO_UTM.transform(x, y), g)

def to_wgs(g):
    return transform(lambda x, y: TO_WGS.transform(x, y), g)

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def area_m2(g):
    if g is None or g.is_empty:
        return 0.0
    return abs(to_utm(g).area)

def dissolve_group(items):
    """items: list of (code, name, parent, shapely geom WGS)."""
    geoms_utm = []
    for _, _, _, g in items:
        gu = to_utm(g)
        if not gu.is_valid:
            gu = make_valid(gu)
        geoms_utm.append(gu)
    # snap each to a reference grid via unary_union of snapped pieces
    ref = unary_union(geoms_utm)
    snapped = [snap(g, ref, SNAP_M) for g in geoms_utm]
    u = unary_union(snapped)
    if not u.is_valid:
        u = make_valid(u)
    return to_wgs(u)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--out", default="artifacts/dissolved")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with open(args.geojson) as f:
        feats = json.load(f)["features"]

    villages = []
    for ft in feats:
        p = ft["properties"]
        g = shape(ft["geometry"])
        if not g.is_valid:
            g = make_valid(g)
        villages.append({
            "code": str(p.get("village_id") or "").strip(),
            "name": (p.get("village") or "").strip(),
            "cell": str(p.get("cell_id") or "").strip(),
            "sector": str(p.get("sector_id") or "").strip(),
            "district": str(p.get("district_id") or "").strip(),
            "province": str(p.get("province_id") or "").strip(),
            "geom": g,
            "cell_name": (p.get("cell") or "").strip(),
            "sector_name": (p.get("sector") or "").strip(),
            "district_name": (p.get("district") or "").strip(),
            "province_name": (p.get("province") or "").strip(),
        })

    print(f"villages={len(villages)}", flush=True)

    levels_spec = [
        ("cell", "cell", "cell_name", "sector"),
        ("sector", "sector", "sector_name", "district"),
        ("district", "district", "district_name", "province"),
        ("province", "province", "province_name", None),
    ]

    dissolved = {}
    metrics = {"snap_m": SNAP_M, "crs_area": "EPSG:32736", "levels": {}}

    for level, code_key, name_key, parent_key in levels_spec:
        groups = collections.defaultdict(list)
        for v in villages:
            code = v[code_key]
            if not code:
                continue
            parent = v[parent_key] if parent_key else None
            groups[code].append((code, v[name_key], parent, v["geom"]))

        features = []
        parent_vs_children = []
        sibling_overlaps = []
        invalid = 0
        codes = sorted(groups.keys())

        # dissolve each group
        geoms = {}
        meta = {}
        for code in codes:
            items = groups[code]
            name = items[0][1]
            parent = items[0][2]
            g = dissolve_group(items)
            if not g.is_valid:
                g = make_valid(g)
                if not g.is_valid:
                    invalid += 1
            geoms[code] = g
            meta[code] = {"name": name, "parent_code": parent, "n_children": len(items)}
            child_area = sum(area_m2(it[3]) for it in items)
            parent_area = area_m2(g)
            rel = abs(parent_area - child_area) / max(child_area, 1.0)
            parent_vs_children.append(rel)

        # sibling overlap within same parent
        by_parent = collections.defaultdict(list)
        for code, m in meta.items():
            by_parent[m["parent_code"]].append(code)
        for parent, kids in by_parent.items():
            for i in range(len(kids)):
                for j in range(i + 1, len(kids)):
                    a, b = geoms[kids[i]], geoms[kids[j]]
                    inter = area_m2(a.intersection(b))
                    parent_a = area_m2(a)
                    frac = inter / max(parent_a, 1.0)
                    if inter > 1.0:
                        sibling_overlaps.append(frac)

        for code in codes:
            features.append({
                "type": "Feature",
                "properties": {
                    "code": code,
                    "name": meta[code]["name"],
                    "parent_code": meta[code]["parent_code"],
                    "level": level,
                    "n_children": meta[code]["n_children"],
                },
                "geometry": mapping(geoms[code]),
            })

        payload = json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")).encode()
        gzpath = out / f"{level}s.geojson.gz"
        with gzip.open(gzpath, "wb", compresslevel=9) as f:
            f.write(payload)

        metrics["levels"][level] = {
            "count": len(features),
            "bytes_gz": gzpath.stat().st_size,
            "sha256": sha256_bytes(gzpath.read_bytes()),
            "invalid_geoms": invalid,
            "max_rel_area_diff_parent_vs_children": max(parent_vs_children) if parent_vs_children else 0,
            "mean_rel_area_diff": sum(parent_vs_children) / max(len(parent_vs_children), 1),
            "max_sibling_overlap_frac": max(sibling_overlaps) if sibling_overlaps else 0,
            "n_sibling_pairs_with_overlap": len(sibling_overlaps),
        }
        print(json.dumps({"level": level, **metrics["levels"][level]}), flush=True)
        dissolved[level] = geoms

    # country = union of provinces
    prov_items = [(c, meta.get("name", ""), None, g) for c, g in dissolved["province"].items()]
    # reuse dissolve_group path via list of geoms
    country_g = dissolve_group([(c, "", None, g) for c, g in dissolved["province"].items()])
    if not country_g.is_valid:
        country_g = make_valid(country_g)
    cfeat = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"code": "RW", "name": "Rwanda", "parent_code": None, "level": "country"},
            "geometry": mapping(country_g),
        }],
    }
    cbytes = json.dumps(cfeat, separators=(",", ":")).encode()
    cpath = out / "country.geojson.gz"
    with gzip.open(cpath, "wb", compresslevel=9) as f:
        f.write(cbytes)
    metrics["levels"]["country"] = {
        "count": 1,
        "bytes_gz": cpath.stat().st_size,
        "sha256": sha256_bytes(cpath.read_bytes()),
        "area_m2": area_m2(country_g),
        "invalid_geoms": 0 if country_g.is_valid else 1,
    }

    # parent code consistency: every village cell/sector/district/province present in dissolved keys
    missing = {"cell": [], "sector": [], "district": [], "province": []}
    for v in villages:
        for level, key in (("cell", "cell"), ("sector", "sector"), ("district", "district"), ("province", "province")):
            if v[key] and v[key] not in dissolved[level]:
                missing[level].append(v["code"])
    metrics["parent_code_consistency"] = {k: {"missing_codes": len(set(v)), "examples": list(set(v))[:10]} for k, v in missing.items()}

    metrics["built_at"] = datetime.now(timezone.utc).isoformat()
    metrics["source"] = "data/rwanda_villages_full.geojson"
    metrics["village_count"] = len(villages)
    metrics["expected"] = {"cell": 2148, "sector": 416, "district": 30, "province": 5, "country": 1}

    man = out / "manifest.json"
    man.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))

    # gate soft warnings
    for level, m in metrics["levels"].items():
        if level == "country":
            continue
        if m.get("invalid_geoms", 0) != 0:
            print(f"WARN invalid {level}")
        if m.get("max_sibling_overlap_frac", 0) >= 0.001:
            print(f"WARN sibling overlap {level} {m['max_sibling_overlap_frac']}")

if __name__ == "__main__":
    main()
