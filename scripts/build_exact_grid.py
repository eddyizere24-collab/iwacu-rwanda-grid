#!/usr/bin/env python3
"""Exact lattice + hierarchical pure-merge. Binary IRG2 (string keys).

CHANGED 2026-11-01 GROK: pure cells must also have cell centroid inside the sole village
(rejects false pure at borders that caused cross-district c/d fails); see docs/HANDOFF.md
"""
from __future__ import annotations
import argparse, json, gzip, collections, math, struct, sys
from pathlib import Path
from datetime import datetime, timezone
from shapely.geometry import shape, box, Point
from shapely.ops import transform
from shapely.validation import make_valid
from shapely.prepared import prep
import pygeohash as pgh
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grid_codec import write_binary_chunk

VERSION = "2026.11.01.irg2p"
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32736", always_xy=True)
BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"

def encode(lat, lon, p):
    return pgh.encode(lat, lon, precision=p)

def gh_bbox(gh):
    lat, lon, lat_err, lon_err = pgh.decode_exactly(gh)
    return (lon - lon_err, lat - lat_err, lon + lon_err, lat + lat_err)

def lattice_step(precision):
    _, _, lat_err, lon_err = pgh.decode_exactly(pgh.encode(-2.0, 30.0, precision))
    return 2 * lat_err, 2 * lon_err

def area_utm(geom):
    if geom is None or geom.is_empty:
        return 0.0
    try:
        return abs(transform(lambda x, y: TO_UTM.transform(x, y), geom).area)
    except Exception:
        return 0.0

def cells_covering_polygon(poly, precision):
    dlat, dlon = lattice_step(precision)
    minx, miny, maxx, maxy = poly.bounds
    minx -= dlon; maxx += dlon; miny -= dlat; maxy += dlat
    i0 = math.floor(miny / dlat) - 1
    i1 = math.ceil(maxy / dlat) + 1
    j0 = math.floor(minx / dlon) - 1
    j1 = math.ceil(maxx / dlon) + 1
    prepared = prep(poly)
    seen = {}
    for i in range(i0, i1 + 1):
        lat_c = (i + 0.5) * dlat
        if not (-90 < lat_c < 90):
            continue
        for j in range(j0, j1 + 1):
            lon_c = (j + 0.5) * dlon
            if not (-180 < lon_c < 180):
                continue
            gh = encode(lat_c, lon_c, precision)
            if gh in seen:
                continue
            bb = box(*gh_bbox(gh))
            if prepared.intersects(bb):
                seen[gh] = bb
    return seen

def refine_mixed(gh, village_geoms, village_ids, precision_next):
    parent_bb = box(*gh_bbox(gh))
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
                a = area_utm(g.intersection(cb))
                if a > 1e-6:
                    areas[vid] = a
            if not areas:
                continue
            total = sum(areas.values())
            ranked = sorted(areas.items(), key=lambda x: -x[1])
            shares = [(v, a / total) for v, a in ranked[:5]]
            pure = len(areas) == 1
            if pure:
                lat, lon, _, _ = pgh.decode_exactly(child)
                if not village_geoms[village_ids.index(ranked[0][0])].covers(Point(lon, lat)):
                    pure = False
            result[child] = {"shares": shares, "pure": pure, "prec": precision_next}
    return result

def hierarchical_merge(store: dict):
    for prec in (9, 8, 7, 6, 5):
        parents = collections.defaultdict(list)
        for gh in list(store.keys()):
            if len(gh) != prec:
                continue
            parents[gh[:-1]].append(gh)
        for parent, kids in parents.items():
            if len(parent) < 4:
                continue
            expected = {parent + c for c in BASE32}
            if set(kids) != expected:
                continue
            if any(not store[k]["pure"] for k in kids):
                continue
            vids = {store[k]["shares"][0][0] for k in kids}
            if len(vids) != 1:
                continue
            vid = next(iter(vids))
            store[parent] = {"pure": True, "shares": [(vid, 1.0)], "prec": len(parent)}
            for k in kids:
                del store[k]
    return store

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
            a = area_utm(g.intersection(bb))
            if a > 1e-6:
                cell_areas[gh][ids[i]] += a

    leaves = {}
    mixed7 = []
    for gh, ctr in cell_areas.items():
        total = sum(ctr.values())
        ranked = sorted(ctr.items(), key=lambda x: -x[1])
        shares = [(v, a / total) for v, a in ranked[:5]]
        pure = len(ctr) == 1
        if pure:
            lat, lon, _, _ = pgh.decode_exactly(gh)
            vid = ranked[0][0]
            if vid not in id_to_idx or not vgeoms[id_to_idx[vid]].covers(Point(lon, lat)):
                pure = False
        if pure:
            leaves[gh] = {"pure": True, "shares": shares[:1], "prec": 7}
        else:
            mixed7.append(gh)
            leaves[gh] = {"pure": False, "shares": shares, "prec": 7}

    for gh in mixed7:
        vids = [v for v, _ in cell_areas[gh].most_common()]
        geoms = [vgeoms[id_to_idx[v]] for v in vids if v in id_to_idx]
        vids = [v for v in vids if v in id_to_idx]
        for child, info in refine_mixed(gh, geoms, vids, 8).items():
            if info["pure"]:
                leaves[child] = {"pure": True, "shares": info["shares"][:1], "prec": 8}
            else:
                leaves[child] = {"pure": False, "shares": info["shares"], "prec": 8}
                for leaf, info9 in refine_mixed(child, geoms, vids, 9).items():
                    leaves[leaf] = {
                        "pure": info9["pure"],
                        "shares": info9["shares"][:1] if info9["pure"] else info9["shares"],
                        "prec": 9,
                    }

    store = hierarchical_merge(leaves)
    return store, {m["id"]: m for m in vmeta}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--district", default=None)
    ap.add_argument("--out", default="artifacts/exact_out")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "gh6").mkdir(exist_ok=True)

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

    vids = sorted({v for info in all_cells.values() for v, _ in info["shares"]})
    village_index = {v: i for i, v in enumerate(vids)}

    root_cells = {gh: info for gh, info in all_cells.items() if info["pure"] and len(gh) <= 5}
    refined = {gh: info for gh, info in all_cells.items() if gh not in root_cells}
    by_gh6 = collections.defaultdict(dict)
    for gh, info in refined.items():
        by_gh6[gh[:6] if len(gh) >= 6 else gh.ljust(6, "0")[:6]].update({gh: info})

    root_payload = {
        "v": VERSION,
        "villages": {v: all_meta[v] for v in vids if v in all_meta},
        "vid_order": vids,
        "merge_rule": "all_32_children_exist_pure_same_village",
        "pure_rule": "exclusive_single_village_and_centroid_inside",
        "format": "IRG2",
    }
    root_bin = write_binary_chunk(root_cells, village_index)
    root_json = json.dumps(root_payload, separators=(",", ":")).encode()
    root_path = out / "root.bin.gz"
    with gzip.open(root_path, "wb", compresslevel=9) as f:
        f.write(struct.pack(">I", len(root_json)) + root_json + root_bin)

    gh6_sizes = []
    for prefix, cells in sorted(by_gh6.items()):
        raw = write_binary_chunk(cells, village_index)
        p = out / "gh6" / f"{prefix}.bin.gz"
        with gzip.open(p, "wb", compresslevel=9) as f:
            f.write(raw)
        gh6_sizes.append(p.stat().st_size)

    gh6_sorted = sorted(gh6_sizes) if gh6_sizes else [0]
    man = {
        "dataset_version": VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "crs_area": "EPSG:32736",
        "pure_rule": "exclusive_single_village_and_centroid_inside",
        "merge": "all_32_children_exist_pure_same_village_up_to_gh4",
        "format": "IRG2_string_keys_gz",
        "village_total": len(all_meta),
        "cells_total": len(all_cells),
        "pure_cells": sum(1 for c in all_cells.values() if c["pure"]),
        "root_gz_bytes": root_path.stat().st_size,
        "gh6_file_count": len(gh6_sizes),
        "gh6_p50": gh6_sorted[len(gh6_sorted)//2],
        "gh6_p95": gh6_sorted[int(0.95 * (len(gh6_sorted)-1))] if len(gh6_sorted) > 1 else gh6_sorted[0],
        "gh6_max": max(gh6_sorted),
    }
    json.dump(man, open(out / "manifest.json", "w"), indent=2)
    print(json.dumps(man, indent=2))
    print("DONE IRG2 pure-centroid")

if __name__ == "__main__":
    main()
