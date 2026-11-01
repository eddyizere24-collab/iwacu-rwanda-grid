#!/usr/bin/env python3
"""For 20 random gh6 files: first 10 keys, lengths, prefix match."""
from __future__ import annotations
import argparse, json, random, sys
from pathlib import Path
from grid_codec import load_root, load_gh6_file

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="artifacts/exact_out")
    ap.add_argument("--out", default="data/key_consistency.json")
    args = ap.parse_args()
    out = Path(args.out_dir)
    meta, root_cells, vid_order = load_root(out / "root.bin.gz")
    files = sorted((out / "gh6").glob("*.bin.gz"))
    rng = random.Random(20261031)
    sample = files if len(files) <= 20 else rng.sample(files, 20)
    mismatches = []
    rows = []
    for p in sample:
        prefix = p.stem
        cells = load_gh6_file(p, vid_order)
        keys = sorted(cells.keys())[:10]
        row = {"file": p.name, "prefix": prefix, "n_cells": len(cells), "first_keys": []}
        for k in keys:
            ok = k.startswith(prefix)
            row["first_keys"].append({"key": k, "len": len(k), "prefix_ok": ok})
            if not ok:
                mismatches.append({"file": p.name, "key": k, "prefix": prefix})
        rows.append(row)
    # also check root keys lengths
    root_lens = {}
    for k in root_cells:
        root_lens[len(k)] = root_lens.get(len(k), 0) + 1
    report = {
        "gh6_files_total": len(files),
        "sampled": len(sample),
        "prefix_mismatches": len(mismatches),
        "mismatch_examples": mismatches[:10],
        "files": rows,
        "root_key_length_hist": root_lens,
        "root_n": len(root_cells),
        "pass": len(mismatches) == 0,
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["pass"] else 1)

if __name__ == "__main__":
    main()
