#!/usr/bin/env python3
"""Encode in-memory cell dict with binary writer, decode, compare 100k random lookups."""
from __future__ import annotations
import argparse, json, gzip, random, struct, sys
from pathlib import Path
from grid_codec import write_binary_chunk, read_binary_chunk, longest_prefix
import pygeohash as pgh

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells-json", help="JSON list of {g,pure,t:[{v,s}],prec} or chunks_gh4 dir")
    ap.add_argument("--chunks-dir", default=None)
    ap.add_argument("--out", default="data/codec_roundtrip.json")
    args = ap.parse_args()

    cells = {}
    villages = {}
    if args.chunks_dir:
        for p in Path(args.chunks_dir).glob("*.json.gz"):
            with gzip.open(p, "rt") as f:
                ch = json.load(f)
            for c in ch.get("cells", []):
                cells[c["g"]] = {
                    "pure": c["pure"],
                    "shares": [(t["v"], t["s"]) for t in c["t"]],
                    "prec": c.get("prec", len(c["g"])),
                }
            villages.update(ch.get("villages", {}))
    elif args.cells_json:
        data = json.loads(Path(args.cells_json).read_text())
        for c in data:
            cells[c["g"]] = {
                "pure": c["pure"],
                "shares": [(t["v"], t["s"]) for t in c["t"]],
                "prec": c.get("prec", len(c["g"])),
            }
    else:
        # synthetic mixed lengths
        for i, gh in enumerate(["kx", "kxtk", "kxtkg", "kxtkgv", "kxtkgv5", "kxtkgv5r", "kxtkgv5r8"]):
            cells[gh] = {"pure": True, "shares": [(f"v{i}", 1.0)], "prec": len(gh)}

    vids = sorted({v for info in cells.values() for v, _ in info["shares"]})
    vindex = {v: i for i, v in enumerate(vids)}
    raw = write_binary_chunk(cells, vindex)
    decoded = read_binary_chunk(raw, vids)

    key_miss = sorted(set(cells) - set(decoded))
    key_extra = sorted(set(decoded) - set(cells))
    share_dis = []
    for gh, info in cells.items():
        if gh not in decoded:
            continue
        a = info["shares"][0][0]
        b = decoded[gh]["shares"][0][0]
        if a != b or info["pure"] != decoded[gh]["pure"]:
            share_dis.append({"gh": gh, "json_v": a, "bin_v": b, "json_pure": info["pure"], "bin_pure": decoded[gh]["pure"]})

    rng = random.Random(42)
    disagree = 0
    examples = []
    # sample random points near Rwanda
    for _ in range(100000):
        lat = rng.uniform(-2.9, -1.0)
        lon = rng.uniform(28.8, 30.9)
        gh9 = pgh.encode(lat, lon, 9)
        kj, ij = longest_prefix(gh9, cells)
        kb, ib = longest_prefix(gh9, decoded)
        vj = ij["shares"][0][0] if ij else None
        vb = ib["shares"][0][0] if ib else None
        if kj != kb or vj != vb:
            disagree += 1
            if len(examples) < 10:
                examples.append({"lat": lat, "lng": lon, "gh9": gh9,
                                 "json_key": kj, "bin_key": kb, "json_v": vj, "bin_v": vb})

    report = {
        "n_cells": len(cells),
        "key_missing_after_decode": len(key_miss),
        "key_extra": len(key_extra),
        "share_disagreements": len(share_dis),
        "share_examples": share_dis[:10],
        "lookup_disagree_100k": disagree,
        "lookup_examples": examples,
        "pass": len(key_miss) == 0 and disagree == 0 and len(share_dis) == 0,
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["pass"] else 1)

if __name__ == "__main__":
    main()
