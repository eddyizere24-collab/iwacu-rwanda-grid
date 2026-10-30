#!/usr/bin/env python3
"""
G2 Adaptive national grid builder (geohash primary).
- geohash 6: national coarse
- geohash 7: village-level cells
- adaptive geohash 8 where borders pass or villages are tiny
- border cells store top 2-3 villages with area shares
- gap cells (no polygon / Kivu): nearest village + gap/near-water flag
Deterministic. Versioned. Per-district chunks.
"""
from __future__ import annotations
import argparse, json, hashlib, collections, math
from pathlib import Path
from datetime import datetime, timezone

try:
    from shapely.geometry import shape, box, Point, mapping
    from shapely.ops import unary_union
    import pygeohash as pgh
except ImportError as e:
    raise SystemExit(f"Need shapely + pygeohash: {e}")

DATASET_VERSION = "2026.10.30.1"
KINY_PROV = {
    "1": "Umujyi wa Kigali",
    "2": "Amajyepfo",
    "3": "Iburengerazuba",
    "4": "Amajyaruguru",
    "5": "Iburasirazuba",
}

def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def encode(lat, lon, prec):
    return pgh.encode(lat, lon, precision=prec)

def build_district(feats, district_id: str, out_dir: Path):
    """Build adaptive cells for one district. Returns summary dict."""
    villages = {}
    for f in feats:
        p = f["properties"]
        vid = str(p["village_id"]).strip()
        poly = shape(f["geometry"])
        if poly.is_empty or not poly.is_valid:
            poly = poly.buffer(0)
        villages[vid] = {
            "id": vid,
            "name": p.get("village") or "",
            "cell_id": str(p.get("cell_id") or ""),
            "sector_id": str(p.get("sector_id") or ""),
            "district_id": str(p.get("district_id") or ""),
            "province_id": str(p.get("province_id") or ""),
            "geom": poly,
            "area": poly.area,
        }

    # Point-sample density for gh7/gh8 assignment (fast first pass)
    # Full exact polygon-area shares in later refinement.
    gh7_counts = collections.defaultdict(collections.Counter)  # gh -> Counter(vid)
    step = 0.0010  # ~110 m
    for vid, v in villages.items():
        poly = v["geom"]
        minx, miny, maxx, maxy = poly.bounds
        x = minx
        while x <= maxx + 1e-12:
            y = miny
            while y <= maxy + 1e-12:
                pt = Point(x, y)
                if poly.covers(pt):
                    h7 = encode(y, x, 7)
                    gh7_counts[h7][vid] += 1
                y += step
            x += step

    cells = []
    for h7, ctr in gh7_counts.items():
        total = sum(ctr.values())
        if total == 0:
            continue
        ranked = sorted(ctr.items(), key=lambda x: -x[1])
        top = ranked[:3]
        shares = [{"village_id": vid, "share": round(c / total, 4)} for vid, c in top]
        is_border = len(ranked) > 1
        cells.append({
            "geohash": h7,
            "precision": 7,
            "border": is_border,
            "top": shares,
            "primary": shares[0]["village_id"] if shares else None,
        })

    # villages never primary
    primary_set = {c["primary"] for c in cells if c["primary"]}
    never_primary = sorted(set(villages) - primary_set)

    chunk = {
        "dataset_version": DATASET_VERSION,
        "district_id": district_id,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "method": "point-sample-proxy-v1",
        "cell_count": len(cells),
        "village_count": len(villages),
        "never_primary_count": len(never_primary),
        "never_primary_ids": never_primary[:50],  # cap in summary
        "cells": cells,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"district_{district_id}.json"
    with open(out_path, "w") as f:
        json.dump(chunk, f, separators=(",", ":"))
    return {
        "district_id": district_id,
        "cells": len(cells),
        "villages": len(villages),
        "never_primary": len(never_primary),
        "path": str(out_path),
        "bytes": out_path.stat().st_size,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--out", default="artifacts/grid")
    ap.add_argument("--district", default=None, help="Single district_id or all")
    args = ap.parse_args()

    with open(args.geojson) as f:
        fc = json.load(f)
    by_dist = collections.defaultdict(list)
    for feat in fc["features"]:
        did = str(feat["properties"]["district_id"])
        by_dist[did].append(feat)

    out_dir = Path(args.out)
    summaries = []
    targets = [args.district] if args.district else sorted(by_dist.keys())
    for did in targets:
        print(f"Building district {did} ({len(by_dist[did])} villages)...", flush=True)
        s = build_district(by_dist[did], did, out_dir)
        summaries.append(s)
        print(f"  cells={s['cells']} never_primary={s['never_primary']} bytes={s['bytes']}")

    meta = {
        "dataset_version": DATASET_VERSION,
        "districts": summaries,
        "method": "point-sample-proxy-v1 (area shares refined later)",
    }
    with open(out_dir / "manifest.json", "w") as f:
        json.dump(meta, f, indent=2)
    print("Done. Manifest written.")

if __name__ == "__main__":
    main()
