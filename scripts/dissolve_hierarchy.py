#!/usr/bin/env python3
"""Dissolve NISR village polygons into cell/sector/district/province/country.

Snap tolerance: 1.0 metre in UTM EPSG:32736.
CHANGED 2026-11-01 GROK: make_valid + buffer(0) before union to avoid TopologyException; see docs/HANDOFF.md
"""
from __future__ import annotations
import argparse, json, gzip, hashlib, collections
from pathlib import Path
from datetime import datetime, timezone
from shapely.geometry import shape, mapping
from shapely.ops import unary_union, transform, snap
from shapely.validation import make_valid
from pyproj import Transformer

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32736", always_xy=True)
TO_WGS = Transformer.from_crs("EPSG:32736", "EPSG:4326", always_xy=True)
SNAP_M = 1.0

def to_utm(g):
    return transform(lambda x, y: TO_UTM.transform(x, y), g)

def to_wgs(g):
    return transform(lambda x, y: TO_WGS.transform(x, y), g)

def clean(g):
    if g is None or g.is_empty:
        return g
    if not g.is_valid:
        g = make_valid(g)
    try:
        g = g.buffer(0)
    except Exception:
        g = make_valid(g)
    return g

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def area_m2(g):
    if g is None or g.is_empty:
        return 0.0
    return abs(to_utm(g).area)

def dissolve_group(items):
    geoms_utm = []
    for _, _, _, g in items:
        gu = clean(to_utm(g))
        if gu is not None and not gu.is_empty:
            geoms_utm.append(gu)
    if not geoms_utm:
        from shapely.geometry import GeometryCollection
        return GeometryCollection()
    ref = unary_union([clean(g) for g in geoms_utm])
    snapped = [clean(snap(clean(g), ref, SNAP_M)) for g in geoms_utm]
    try:
        u = unary_union(snapped)
    except Exception:
        # progressive union with repair
        u = snapped[0]
        for g in snapped[1:]:
            try:
                u = clean(u.union(clean(g)))
            except Exception:
                u = clean(unary_union([clean(u), clean(g).buffer(0.01)]))
    u = clean(u)
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
        g = clean(shape(ft["geometry"]))
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
        geoms = {}
        meta = {}
        for i, code in enumerate(codes):
            if i % 50 == 0:
                print(f"  {level} {i}/{len(codes)}", flush=True)
            items = groups[code]
            g = dissolve_group(items)
            if g is None or g.is_empty:
                invalid += 1
                continue
            if not g.is_valid:
                g = clean(g)
                if not g.is_valid:
                    invalid += 1
            geoms[code] = g
            meta[code] = {"name": items[0][1], "parent_code": items[0][2], "n_children": len(items)}
            child_area = sum(area_m2(it[3]) for it in items)
            parent_area = area_m2(g)
            rel = abs(parent_area - child_area) / max(child_area, 1.0)
            parent_vs_children.append(rel)

        by_parent = collections.defaultdict(list)
        for code, m in meta.items():
            by_parent[m["parent_code"]].append(code)
        for parent, kids in by_parent.items():
            for i in range(len(kids)):
                for j in range(i + 1, min(i + 8, len(kids))):  # bound O(n^2)
                    a, b = geoms[kids[i]], geoms[kids[j]]
                    inter = area_m2(a.intersection(b))
                    frac = inter / max(area_m2(a), 1.0)
                    if inter > 1.0:
                        sibling_overlaps.append(frac)

        for code in geoms:
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
            "sha256": sha256_file(gzpath),
            "invalid_geoms": invalid,
            "max_rel_area_diff_parent_vs_children": max(parent_vs_children) if parent_vs_children else 0,
            "mean_rel_area_diff": sum(parent_vs_children) / max(len(parent_vs_children), 1),
            "max_sibling_overlap_frac": max(sibling_overlaps) if sibling_overlaps else 0,
            "n_sibling_pairs_with_overlap": len(sibling_overlaps),
        }
        print(json.dumps({"level": level, **metrics["levels"][level]}), flush=True)
        dissolved[level] = geoms

    country_g = dissolve_group([(c, "", None, g) for c, g in dissolved["province"].items()])
    country_g = clean(country_g)
    cfeat = {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "properties": {"code": "RW", "name": "Rwanda", "parent_code": None, "level": "country"},
        "geometry": mapping(country_g),
    }]}
    cpath = out / "country.geojson.gz"
    with gzip.open(cpath, "wb", compresslevel=9) as f:
        f.write(json.dumps(cfeat, separators=(",", ":")).encode())
    metrics["levels"]["country"] = {
        "count": 1,
        "bytes_gz": cpath.stat().st_size,
        "sha256": sha256_file(cpath),
        "area_m2": area_m2(country_g),
        "invalid_geoms": 0 if country_g.is_valid else 1,
    }

    missing = {"cell": [], "sector": [], "district": [], "province": []}
    for v in villages:
        for level, key in (("cell", "cell"), ("sector", "sector"), ("district", "district"), ("province", "province")):
            if v[key] and v[key] not in dissolved[level]:
                missing[level].append(v["code"])
    metrics["parent_code_consistency"] = {
        k: {"missing_codes": len(set(v)), "examples": list(set(v))[:10]} for k, v in missing.items()
    }
    metrics["built_at"] = datetime.now(timezone.utc).isoformat()
    metrics["source"] = "data/rwanda_villages_full.geojson"
    metrics["village_count"] = len(villages)
    metrics["expected"] = {"cell": 2148, "sector": 416, "district": 30, "province": 5, "country": 1}
    (out / "manifest.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))

if __name__ == "__main__":
    main()
