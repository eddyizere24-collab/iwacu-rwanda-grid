#!/usr/bin/env python3
"""Find parent keys whose stored villages belong to more than one district."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from grid_codec import ShippedIndex

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="artifacts/exact_out")
    ap.add_argument("--out", default="data/district_collision.json")
    args = ap.parse_args()
    idx = ShippedIndex(Path(args.out_dir))
    for p in (Path(args.out_dir) / "gh6").glob("*.bin.gz"):
        idx._ensure_gh6(p.stem)
    villages = idx.meta.get("villages", {})

    def district_of(vid):
        m = villages.get(vid) or {}
        return str(m.get("d") or "?")

    collisions = []
    for gh, info in idx.all.items():
        dists = set()
        for v, _s in info["shares"]:
            dists.add(district_of(v))
        if len(dists) > 1:
            collisions.append({
                "key": gh,
                "len": len(gh),
                "pure": info["pure"],
                "districts": sorted(dists),
                "villages": [v for v, _ in info["shares"]],
            })

    report = {
        "n_cells": len(idx.all),
        "n_collisions": len(collisions),
        "examples": collisions[:10],
        "pass": True,  # multi-district mixed border cells are allowed; pure collisions are bugs
        "pure_collisions": sum(1 for c in collisions if c["pure"]),
    }
    report["pass"] = report["pure_collisions"] == 0
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["pass"] else 1)

if __name__ == "__main__":
    main()
