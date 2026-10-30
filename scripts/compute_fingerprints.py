#!/usr/bin/env python3
"""Compute ID fingerprints from GeoJSON or attrs."""
import json, hashlib, sys
from pathlib import Path

def md5_ids(ids):
    return hashlib.md5(",".join(sorted(ids)).encode()).hexdigest()

def main(path):
    with open(path) as f:
        fc = json.load(f)
    feats = fc.get("features") or fc  # list or FeatureCollection
    if isinstance(feats, dict):
        feats = feats.get("features", [])
    levels = {k: set() for k in ("province", "district", "sector", "cell", "village")}
    key = {"province": "province_id", "district": "district_id", "sector": "sector_id",
           "cell": "cell_id", "village": "village_id"}
    for f in feats:
        p = f.get("properties") or f
        for lev, fld in key.items():
            levels[lev].add(str(p.get(fld) or "").strip())
    for lev in levels:
        ids = levels[lev]
        print(f"{lev}\t{len(ids)}\t{md5_ids(ids)}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/rwanda_villages_full.geojson")
