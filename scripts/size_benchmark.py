#!/usr/bin/env python3
"""KB downloaded per lookup: root + needed gh6 refined files."""
from __future__ import annotations
import argparse, json, gzip, random, statistics
from pathlib import Path
import pygeohash as pgh

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="artifacts/exact_out")
    ap.add_argument("--out", default="data/size_benchmark.json")
    args = ap.parse_args()
    out = Path(args.out_dir)
    root = out / "root.bin.gz"
    gh6_dir = out / "gh6"
    root_kb = root.stat().st_size / 1024 if root.exists() else 0
    files = list(gh6_dir.glob("*.bin.gz")) if gh6_dir.exists() else []
    sizes = sorted(f.stat().st_size / 1024 for f in files)

    def lookup_kb(lat, lon, sigma_m):
        # root always; if sigma<=150 need finest leaf -> gh6 file of point
        kb = root_kb
        if sigma_m <= 150:
            pref = pgh.encode(lat, lon, 6)
            p = gh6_dir / f"{pref}.bin.gz"
            if p.exists():
                kb += p.stat().st_size / 1024
            else:
                # neighbors for border
                for c in "0123456789bcdefghjkmnpqrstuvwxyz":
                    p2 = gh6_dir / f"{pref[:5]}{c}.bin.gz"
                    if p2.exists():
                        kb += p2.stat().st_size / 1024
                        break
        else:
            # summary: root only (gh5 merged lives in root)
            pass
        return kb

    rng = random.Random(42)
    kigali = [(rng.uniform(-2.0, -1.85), rng.uniform(30.0, 30.2)) for _ in range(200)]
    rural = [(rng.uniform(-2.5, -1.6), rng.uniform(29.0, 29.8)) for _ in range(200)]

    def stats(pts, sigma):
        vals = [lookup_kb(la, lo, sigma) for la, lo in pts]
        vals.sort()
        return {
            "p50": round(vals[len(vals)//2], 2),
            "p95": round(vals[int(0.95 * (len(vals)-1))], 2),
            "max": round(max(vals), 2),
            "mean": round(sum(vals) / len(vals), 2),
        }

    report = {
        "root_gz_kb": round(root_kb, 2),
        "gh6_file_count": len(files),
        "gh6_p50_kb": round(sizes[len(sizes)//2], 2) if sizes else 0,
        "gh6_p95_kb": round(sizes[int(0.95*(len(sizes)-1))], 2) if sizes else 0,
        "gh6_max_kb": round(max(sizes), 2) if sizes else 0,
        "lookups": {
            "kigali_s20": stats(kigali, 20),
            "kigali_s100": stats(kigali, 100),
            "kigali_s500": stats(kigali, 500),
            "rural_s20": stats(rural, 20),
            "rural_s100": stats(rural, 100),
            "rural_s500": stats(rural, 500),
        },
    }
    mx = max(v["max"] for v in report["lookups"].values())
    report["max_lookup_kb"] = mx
    report["exceeds_150kb"] = mx > 150
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
