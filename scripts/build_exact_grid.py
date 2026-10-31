#!/usr/bin/env python3
"""Exact-geometry geohash grid: no sampling. Area EPSG:32736. PURE if >=99.9% one village. MIXED->gh8/gh9."""
from __future__ import annotations
import argparse, json, gzip, hashlib, collections
from pathlib import Path
from datetime import datetime, timezone
from shapely.geometry import shape, box, Point
from shapely.ops import transform
from shapely.validation import make_valid
import pygeohash as pgh
from pyproj import Transformer

VERSION = "2026.10.31.exact1"
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32736", always_xy=True)
PURE_FRAC = 0.999

def encode(lat, lon, p):
    return pgh.encode(lat, lon, precision=p)

def gh_bbox(gh):
    lat, lon, lat_err, lon_err = pgh.decode_exactly(gh)
    return (lon - lon_err, lat - lat_err, lon + lon_err, lat + lat_err)

def area_utm(geom):
    if geom is None or geom.is_empty:
        return 0.0
    try:
        g = transform(lambda x, y: TO_UTM.transform(x, y), geom)
        return abs(g.area)
    except Exception:
        return 0.0

def cells_for_polygon(poly, precision=7):
    minx, miny, maxx, maxy = poly.bounds
    step = 0.0006 if precision >= 8 else 0.0012
    if precision >= 9:
        step = 0.00015
    seen = set()
    x = minx
    while x <= maxx + 1e-12:
        y = miny
        while y <= maxy + 1e-12:
            if poly.intersects(Point(x, y)) or poly.covers(Point(x, y)):
                seen.add(encode(y, x, precision))
            y += step
        x += step
    for x in (minx, maxx):
        for y in (miny, maxy):
            seen.add(encode(y, x, precision))
    out = []
    for gh in seen:
        bb = box(*gh_bbox(gh))
        if poly.intersects(bb):
            out.append(gh)
    return out

def refine_cell(gh, village_geoms, village_ids, precision_next):
    minx, miny, maxx, maxy = gh_bbox(gh)
    step = (maxx - minx) / 4.0
    leaves = {}
    x = minx + step / 2
    while x < maxx:
        y = miny + step / 2
        while y < maxy:
            leaves[encode(y, x, precision_next)] = None
            y += step
        x += step
    result = {}
    for child in leaves:
        cb = box(*gh_bbox(child))
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
        result[child] = {"t": shares, "pure": pure}
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
    cell_areas = collections.defaultdict(lambda: collections.Counter())
    for i, g in enumerate(vgeoms):
        for gh in cells_for_polygon(g, 7):
            try:
                a = area_utm(g.intersection(box(*gh_bbox(gh))))
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
        geoms_here = [vgeoms[ids.index(v)] for v in vids_here if v in ids]
        leaves = refine_cell(gh, geoms_here, vids_here, 8)
        still_mixed = []
        for child, info in leaves.items():
            if info["pure"]:
                cells[child] = {"t": info["t"][:1], "pure": True, "prec": 8}
            else:
                still_mixed.append(child)
                cells[child] = {"t": info["t"], "pure": False, "prec": 8}
        for child in still_mixed:
            for leaf, info in refine_cell(child, geoms_here, vids_here, 9).items():
                cells[leaf] = {"t": info["t"][:1] if info["pure"] else info["t"], "pure": info["pure"], "prec": 9}
    return cells, {m["id"]: m for m in vmeta}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--district", default=None)
    ap.add_argument("--out", default="artifacts/exact_out")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    chunk_dir = out / "chunks_gh4"; chunk_dir.mkdir(exist_ok=True)
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
        all_cells.update(cells); all_meta.update(meta)
        print(f"  cells={len(cells)} pure={sum(1 for c in cells.values() if c['pure'])}", flush=True)
    by_p = collections.defaultdict(list)
    for gh, info in all_cells.items():
        by_p[gh[:4]].append({"g": gh, "t": info["t"], "pure": info["pure"], "prec": info["prec"]})
    manifest_files = []
    for prefix, cells in sorted(by_p.items()):
        vids = {t["v"] for c in cells for t in c["t"]}
        vlookup = {vid: all_meta[vid] for vid in vids if vid in all_meta}
        raw = json.dumps({"v": VERSION, "prefix": prefix, "cells": cells, "villages": vlookup}, separators=(",", ":")).encode()
        gz = chunk_dir / f"{prefix}.json.gz"
        with gzip.open(gz, "wb", compresslevel=9) as f:
            f.write(raw)
        (chunk_dir / f"{prefix}.json").write_bytes(raw)
        manifest_files.append({"file": f"chunks_gh4/{prefix}.json.gz", "bytes_gz": gz.stat().st_size,
                               "sha256": hashlib.sha256(gz.read_bytes()).hexdigest(), "cells": len(cells)})
    pure_n = sum(1 for c in all_cells.values() if c["pure"])
    man = {"dataset_version": VERSION, "built_at": datetime.now(timezone.utc).isoformat(),
           "crs_area": "EPSG:32736", "pure_frac": PURE_FRAC,
           "village_total": len(all_meta), "cells_total": len(all_cells),
           "pure_cells": pure_n, "mixed_cells": len(all_cells) - pure_n,
           "gh4_files": manifest_files,
           "max_chunk_gz": max((f["bytes_gz"] for f in manifest_files), default=0),
           "p95_chunk_gz": sorted(f["bytes_gz"] for f in manifest_files)[int(0.95 * len(manifest_files))] if manifest_files else 0}
    json.dump(man, open(out / "manifest.json", "w"), indent=2)
    json.dump(man, open("data/manifest_exact.json", "w"), indent=2)
    print(json.dumps({k: man[k] for k in ("village_total", "cells_total", "pure_cells", "max_chunk_gz")}, indent=2))
    print("DONE exact build")

if __name__ == "__main__":
    main()
