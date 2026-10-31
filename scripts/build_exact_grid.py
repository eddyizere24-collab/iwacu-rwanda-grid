#!/usr/bin/env python3
"""Exact-geometry geohash grid: FULL lattice enumeration, no centre sampling.
Area CRS: EPSG:32736 (UTM 36S). PURE if >=99.9% of village-covered cell area is one village.
MIXED refined to gh8 then gh9 with the same lattice method.
"""
from __future__ import annotations
import argparse, json, gzip, hashlib, collections, math
from pathlib import Path
from datetime import datetime, timezone
from shapely.geometry import shape, box, Point
from shapely.ops import transform
from shapely.validation import make_valid
from shapely.prepared import prep
import pygeohash as pgh
from pyproj import Transformer

VERSION = "2026.10.31.exact2"
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32736", always_xy=True)
PURE_FRAC = 0.999

# Lattice half-sizes (lat_err, lon_err) from pygeohash decode_exactly at Rwanda latitude
# Full cell size = 2 * err
LATTICE = {
    7: (0.001373291015625 / 2, 0.001373291015625 / 2),  # will recompute from encode
    8: (0.000171661376953125 / 2, 0.00034332275390625 / 2),
    9: (4.291534423828125e-05 / 2, 4.291534423828125e-05 / 2),
}

def encode(lat, lon, p):
    return pgh.encode(lat, lon, precision=p)

def gh_bbox(gh):
    lat, lon, lat_err, lon_err = pgh.decode_exactly(gh)
    return (lon - lon_err, lat - lat_err, lon + lon_err, lat + lat_err)

def lattice_step(precision):
    """Return (dlat, dlon) full cell size at this precision near Rwanda."""
    _, _, lat_err, lon_err = pgh.decode_exactly(pgh.encode(-2.0, 30.0, precision))
    return 2 * lat_err, 2 * lon_err

def area_utm(geom):
    if geom is None or geom.is_empty:
        return 0.0
    try:
        g = transform(lambda x, y: TO_UTM.transform(x, y), geom)
        return abs(g.area)
    except Exception:
        return 0.0

def cells_covering_polygon(poly, precision):
    """Enumerate EVERY geohash cell of given precision whose rectangle intersects poly.

    Uses the regular geohash lattice: walk integer steps of (dlat, dlon) across the
    polygon bbox expanded by one cell, encode each lattice centre, dedupe, then
    confirm intersects with prepared polygon.
    """
    dlat, dlon = lattice_step(precision)
    minx, miny, maxx, maxy = poly.bounds
    # expand by one full cell so edge-touching cells are included
    minx -= dlon
    maxx += dlon
    miny -= dlat
    maxy += dlat
    # snap start to lattice by encoding SW corner and taking its centre, then step
    # Integer indices relative to origin at (0,0) in degrees is fine for local bbox
    i0 = math.floor(miny / dlat) - 1
    i1 = math.ceil(maxy / dlat) + 1
    j0 = math.floor(minx / dlon) - 1
    j1 = math.ceil(maxx / dlon) + 1
    prepared = prep(poly)
    seen = {}
    for i in range(i0, i1 + 1):
        lat_c = (i + 0.5) * dlat
        if lat_c < -90 or lat_c > 90:
            continue
        for j in range(j0, j1 + 1):
            lon_c = (j + 0.5) * dlon
            if lon_c < -180 or lon_c > 180:
                continue
            gh = encode(lat_c, lon_c, precision)
            if gh in seen:
                continue
            bb = box(*gh_bbox(gh))
            if prepared.intersects(bb):
                seen[gh] = bb
    return seen  # gh -> bbox polygon

def refine_mixed(gh, village_geoms, village_ids, precision_next):
    """Subdivide parent cell into full lattice of precision_next intersecting any village."""
    parent_bb = box(*gh_bbox(gh))
    # union of villages clipped to parent for faster tests
    dlat, dlon = lattice_step(precision_next)
    minx, miny, maxx, maxy = parent_bb.bounds
    i0 = math.floor(miny / dlat) - 1
    i1 = math.ceil(maxy / dlat) + 1
    j0 = math.floor(minx / dlon) - 1
    j1 = math.ceil(maxx / dlon) + 1
    result = {}
    for i in range(i0, i1 + 1):
        lat_c = (i + 0.5) * dlat
        for j in range(j0, j1 + 1):
            lon_c = (j + 0.5) * dlon
            child = encode(lat_c, lon_c, precision_next)
            if child in result:
                continue
            cb = box(*gh_bbox(child))
            if not parent_bb.intersects(cb):
                continue
            areas = {}
            for vid, g in zip(village_ids, village_geoms):
                try:
                    a = area_utm(g.intersection(cb))
                except Exception:
                    a = 0.0
                if a > 0:
                    areas[vid] = a
            if not areas:
                continue
            total = sum(areas.values())
            ranked = sorted(areas.items(), key=lambda x: -x[1])
            shares = [{"v": v, "s": round(a / total, 5)} for v, a in ranked[:5]]
            pure = len(areas) == 1 or (ranked[0][1] / total >= PURE_FRAC)
            result[child] = {"t": shares, "pure": pure, "prec": precision_next}
    return result

def build_district(feats):
    vgeoms, vmeta = [], []
    for feat in feats:
        p = feat["properties"]
        g = shape(feat["geometry"])
        if not g.is_valid:
            g = make_valid(g)
        c = g.centroid
        vgeoms.append(g)
        vmeta.append({
            "id": str(p["village_id"]).strip(),
            "n": (p.get("village") or "").strip(),
            "c": str(p.get("cell_id") or "").strip(),
            "s": str(p.get("sector_id") or "").strip(),
            "d": str(p.get("district_id") or "").strip(),
            "p": str(p.get("province_id") or "").strip(),
            "lat": round(c.y, 6), "lon": round(c.x, 6),
        })
    ids = [m["id"] for m in vmeta]
    id_to_idx = {vid: i for i, vid in enumerate(ids)}

    cell_areas = collections.defaultdict(lambda: collections.Counter())
    for i, g in enumerate(vgeoms):
        for gh, bb in cells_covering_polygon(g, 7).items():
            try:
                a = area_utm(g.intersection(bb))
            except Exception:
                a = 0.0
            if a > 0:
                cell_areas[gh][ids[i]] += a

    cells = {}
    mixed_gh7 = []
    for gh, ctr in cell_areas.items():
        total = sum(ctr.values())
        if total <= 0:
            continue
        ranked = sorted(ctr.items(), key=lambda x: -x[1])
        shares = [{"v": v, "s": round(a / total, 5)} for v, a in ranked[:5]]
        pure = len(ctr) == 1 or (ranked[0][1] / total >= PURE_FRAC)
        if pure:
            cells[gh] = {"t": shares[:1], "pure": True, "prec": 7}
        else:
            mixed_gh7.append(gh)
            cells[gh] = {"t": shares, "pure": False, "prec": 7}

    for gh in mixed_gh7:
        vids_here = [v for v, _ in cell_areas[gh].most_common()]
        geoms_here = [vgeoms[id_to_idx[v]] for v in vids_here if v in id_to_idx]
        leaves8 = refine_mixed(gh, geoms_here, vids_here, 8)
        still = []
        for child, info in leaves8.items():
            if info["pure"]:
                cells[child] = {"t": info["t"][:1], "pure": True, "prec": 8}
            else:
                still.append(child)
                cells[child] = {"t": info["t"], "pure": False, "prec": 8}
        for child in still:
            for leaf, info in refine_mixed(child, geoms_here, vids_here, 9).items():
                cells[leaf] = {
                    "t": info["t"][:1] if info["pure"] else info["t"],
                    "pure": info["pure"],
                    "prec": 9,
                }
    return cells, {m["id"]: m for m in vmeta}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--district", default=None)
    ap.add_argument("--out", default="artifacts/exact_out")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    chunk_dir = out / "chunks_gh4"
    chunk_dir.mkdir(exist_ok=True)

    with open(args.geojson) as f:
        feats = json.load(f)["features"]
    by_d = collections.defaultdict(list)
    for feat in feats:
        by_d[str(feat["properties"]["district_id"])].append(feat)
    districts = [args.district] if args.district else sorted(by_d.keys())

    all_cells, all_meta = {}, {}
    for did in districts:
        print(f"District {did} n={len(by_d[did])}...", flush=True)
        cells, meta = build_district(by_d[did])
        all_cells.update(cells)
        all_meta.update(meta)
        pure_n = sum(1 for c in cells.values() if c["pure"])
        print(f"  cells={len(cells)} pure={pure_n}", flush=True)

    by_p = collections.defaultdict(list)
    for gh, info in all_cells.items():
        by_p[gh[:4]].append({"g": gh, "t": info["t"], "pure": info["pure"], "prec": info["prec"]})

    manifest_files = []
    for prefix, cells in sorted(by_p.items()):
        vids = {t["v"] for c in cells for t in c["t"]}
        vlookup = {vid: all_meta[vid] for vid in vids if vid in all_meta}
        raw = json.dumps(
            {"v": VERSION, "prefix": prefix, "cells": cells, "villages": vlookup},
            separators=(",", ":"),
        ).encode()
        gz = chunk_dir / f"{prefix}.json.gz"
        with gzip.open(gz, "wb", compresslevel=9) as f:
            f.write(raw)
        (chunk_dir / f"{prefix}.json").write_bytes(raw)
        manifest_files.append({
            "file": f"chunks_gh4/{prefix}.json.gz",
            "bytes_gz": gz.stat().st_size,
            "sha256": hashlib.sha256(gz.read_bytes()).hexdigest(),
            "cells": len(cells),
        })

    pure_n = sum(1 for c in all_cells.values() if c["pure"])
    man = {
        "dataset_version": VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "crs_area": "EPSG:32736",
        "pure_frac": PURE_FRAC,
        "enumeration": "full_lattice_no_sampling",
        "village_total": len(all_meta),
        "cells_total": len(all_cells),
        "pure_cells": pure_n,
        "mixed_cells": len(all_cells) - pure_n,
        "gh4_files": manifest_files,
        "max_chunk_gz": max((f["bytes_gz"] for f in manifest_files), default=0),
    }
    json.dump(man, open(out / "manifest.json", "w"), indent=2)
    json.dump(man, open("data/manifest_exact.json", "w"), indent=2)
    print(json.dumps({k: man[k] for k in ("village_total", "cells_total", "pure_cells", "max_chunk_gz")}, indent=2))
    print("DONE exact build lattice")

if __name__ == "__main__":
    main()
