#!/usr/bin/env python3
"""Exact lattice grid with hierarchical pure-merge + binary on-disk format.

PURE = exclusive single village. MIXED refined to gh8/gh9.
If all children of a cell are pure and the SAME village, store the parent only
(recursively up to gh4). Binary: sorted geohash keys delta-coded + varint shares.
Chunks: root index (<=~40KB gz) + refined leaves by gh6 prefix.
"""
from __future__ import annotations
import argparse, json, gzip, hashlib, collections, math, struct
from pathlib import Path
from datetime import datetime, timezone
from shapely.geometry import shape, box, Point
from shapely.ops import transform
from shapely.validation import make_valid
from shapely.prepared import prep
import pygeohash as pgh
from pyproj import Transformer

VERSION = "2026.10.31.hier1"
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

def children32(gh):
    return [gh + c for c in BASE32]

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
            result[child] = {"shares": shares, "pure": len(areas) == 1, "prec": precision_next}
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
            a = area_utm(g.intersection(bb))
            if a > 1e-6:
                cell_areas[gh][ids[i]] += a

    # leaf cells at gh7+ refinement
    leaves = {}  # gh -> {pure, shares:[(vid,s)], prec}
    mixed7 = []
    for gh, ctr in cell_areas.items():
        total = sum(ctr.values())
        ranked = sorted(ctr.items(), key=lambda x: -x[1])
        shares = [(v, a / total) for v, a in ranked[:5]]
        if len(ctr) == 1:
            leaves[gh] = {"pure": True, "shares": shares[:1], "prec": 7}
        else:
            mixed7.append(gh)
            leaves[gh] = {"pure": False, "shares": shares, "prec": 7}

    for gh in mixed7:
        vids = [v for v, _ in cell_areas[gh].most_common()]
        geoms = [vgeoms[id_to_idx[v]] for v in vids if v in id_to_idx]
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

    # hierarchical merge: pure same-village children -> parent (gh9..gh4)
    store = dict(leaves)
    for prec in (9, 8, 7, 6, 5):
        parents = collections.defaultdict(list)
        for gh, info in list(store.items()):
            if len(gh) != prec:
                continue
            parents[gh[:-1]].append(gh)
        for parent, kids in parents.items():
            if len(parent) < 4:
                continue
            # need all 32 children present and pure same village OR only pure subset covering
            # Spec: if all 32 children pure and same village -> parent pure
            if len(kids) < 32:
                # partial: still merge if every existing child is pure same vid and no mixed siblings known
                vids = set()
            ok = True
            vids = set()
            for k in kids:
                info = store[k]
                if not info["pure"]:
                    ok = False
                    break
                vids.add(info["shares"][0][0])
            if not ok or len(vids) != 1:
                continue
            if len(kids) < 32:
                # only collapse full 32-child pure blocks (strict)
                continue
            vid = next(iter(vids))
            store[parent] = {"pure": True, "shares": [(vid, 1.0)], "prec": len(parent)}
            for k in kids:
                del store[k]

    return store, {m["id"]: m for m in vmeta}

# ---- binary codec ----
def _uvarint(n: int) -> bytes:
    out = bytearray()
    while n > 0x7F:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n & 0x7F)
    return bytes(out)

def _gh_to_int(gh: str) -> int:
    n = 0
    for c in gh:
        n = n * 32 + BASE32.index(c)
    return n

def write_binary_chunk(cells: dict, village_index: dict[str, int]) -> bytes:
    """Sorted geohash keys delta-coded; pure: flag+vid; mixed: n + (vid,share_q16)."""
    items = sorted(cells.items(), key=lambda x: x[0])
    buf = bytearray()
    buf += b"IRG1"
    buf += _uvarint(len(items))
    prev = 0
    for gh, info in items:
        cur = _gh_to_int(gh)
        buf += _uvarint(cur - prev)
        prev = cur
        buf += bytes([len(gh)])  # precision / key length
        if info["pure"]:
            buf += b"\x01"
            buf += _uvarint(village_index[info["shares"][0][0]])
        else:
            buf += b"\x00"
            shares = info["shares"][:5]
            buf += bytes([len(shares)])
            for vid, s in shares:
                buf += _uvarint(village_index[vid])
                q = max(0, min(65535, int(round(s * 65535))))
                buf += struct.pack(">H", q)
    return bytes(buf)

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

    # village id catalog
    vids = sorted({v for info in all_cells.values() for v, _ in info["shares"]})
    village_index = {v: i for i, v in enumerate(vids)}
    inv_index = {i: v for v, i in village_index.items()}

    # root: pure cells with len<=5 (gh4/gh5) + index of gh6 refined prefixes
    root_cells = {gh: info for gh, info in all_cells.items() if info["pure"] and len(gh) <= 5}
    refined = {gh: info for gh, info in all_cells.items() if gh not in root_cells}

    by_gh6 = collections.defaultdict(dict)
    for gh, info in refined.items():
        by_gh6[gh[:6] if len(gh) >= 6 else gh].update({gh: info})

    # also put pure gh6+ into gh6 files? pure long keys stay in refined files
    sizes = {"root": 0, "gh6": []}

    root_payload = {
        "v": VERSION,
        "villages": {v: all_meta[v] for v in vids if v in all_meta},
        "vid_order": vids,
    }
    root_bin = write_binary_chunk(root_cells, village_index)
    root_json = json.dumps(root_payload, separators=(",", ":")).encode()
    root_path = out / "root.bin.gz"
    with gzip.open(root_path, "wb", compresslevel=9) as f:
        f.write(struct.pack(">I", len(root_json)) + root_json + root_bin)
    sizes["root"] = root_path.stat().st_size

    for prefix, cells in sorted(by_gh6.items()):
        raw = write_binary_chunk(cells, village_index)
        p = out / "gh6" / f"{prefix}.bin.gz"
        with gzip.open(p, "wb", compresslevel=9) as f:
            f.write(raw)
        sizes["gh6"].append(p.stat().st_size)

    # also write a small JSON cell dump for invariants (gh keys + pure + majority)
    inv_cells = []
    for gh, info in all_cells.items():
        inv_cells.append({"g": gh, "pure": info["pure"], "t": [{"v": v, "s": round(s, 5)} for v, s in info["shares"][:3]], "prec": info["prec"]})
    # pack by gh4 for check_invariants compatibility
    by_p = collections.defaultdict(list)
    for c in inv_cells:
        by_p[c["g"][:4]].append(c)
    inv_dir = out / "chunks_gh4"
    inv_dir.mkdir(exist_ok=True)
    for prefix, cells in by_p.items():
        payload = {"v": VERSION, "prefix": prefix, "cells": cells,
                   "villages": {v: all_meta[v] for c in cells for t in c["t"] for v in [t["v"]] if v in all_meta}}
        raw = json.dumps(payload, separators=(",", ":")).encode()
        with gzip.open(inv_dir / f"{prefix}.json.gz", "wb", compresslevel=9) as f:
            f.write(raw)

    gh6_sorted = sorted(sizes["gh6"]) if sizes["gh6"] else [0]
    man = {
        "dataset_version": VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "crs_area": "EPSG:32736",
        "pure_rule": "exclusive_single_village",
        "merge": "full32_children_same_village_up_to_gh4",
        "format": "binary_delta_varint_gz",
        "village_total": len(all_meta),
        "cells_total": len(all_cells),
        "pure_cells": sum(1 for c in all_cells.values() if c["pure"]),
        "root_gz_bytes": sizes["root"],
        "gh6_file_count": len(sizes["gh6"]),
        "gh6_p50": gh6_sorted[len(gh6_sorted)//2],
        "gh6_p95": gh6_sorted[int(0.95 * (len(gh6_sorted)-1))] if len(gh6_sorted) > 1 else gh6_sorted[0],
        "gh6_max": max(gh6_sorted),
    }
    json.dump(man, open(out / "manifest.json", "w"), indent=2)
    print(json.dumps(man, indent=2))
    print("DONE hierarchical binary build")

if __name__ == "__main__":
    main()
