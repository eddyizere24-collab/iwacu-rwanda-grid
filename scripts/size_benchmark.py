#!/usr/bin/env python3
"""Download KB per lookup p50/p95/max for 200 Kigali + 200 rural at acc 20/100/500 m."""
from __future__ import annotations
import argparse, json, math, random
from pathlib import Path
import pygeohash as pgh

def encode(lat, lon, p):
    return pgh.encode(lat, lon, precision=p)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", default="artifacts/algo_out/chunks_gh4")
    ap.add_argument("--pyramid", default="artifacts/algo_out/summary_pyramid.json.gz")
    ap.add_argument("--out", default="data/size_benchmark.json")
    args = ap.parse_args()
    chunk_dir = Path(args.chunks)
    prefix_size = {}
    for p in chunk_dir.glob("*.json.gz"):
        prefix_size[p.name.replace(".json.gz", "")] = p.stat().st_size
    print(f"chunks={len(prefix_size)} max_gz={max(prefix_size.values()) if prefix_size else 0}", flush=True)
    pyr_size = Path(args.pyramid).stat().st_size if Path(args.pyramid).exists() else 0
    rng = random.Random(20261030)
    kigali = [(rng.uniform(-1.98, -1.90), rng.uniform(30.02, 30.12)) for _ in range(200)]
    rural = [(rng.uniform(-2.7, -1.2), rng.uniform(29.0, 30.8)) for _ in range(200)]

    def prefixes_for(lat, lon, acc_m):
        sigma = acc_m / 1.51
        step_m = 150 if sigma <= 450 else 600
        n = max(1, int(math.ceil(3 * max(sigma, 50) / step_m)))
        dlat = step_m / 110574
        dlon = step_m / (111320 * max(0.3, abs(math.cos(math.radians(lat)))))
        prefs = set()
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                prefs.add(encode(lat + i * dlat, lon + j * dlon, 4))
        return prefs

    def measure(points, acc_m):
        kb_list = []
        for lat, lon in points:
            prefs = prefixes_for(lat, lon, acc_m)
            total = sum(prefix_size.get(p, 0) for p in prefs)
            if acc_m >= 500:
                total += pyr_size
            kb_list.append(total / 1024.0)
        kb_list.sort()
        n = len(kb_list)
        return {"p50": round(kb_list[n // 2], 2), "p95": round(kb_list[int(n * 0.95)], 2),
                "max": round(kb_list[-1], 2), "mean": round(sum(kb_list) / n, 2)}

    report = {
        "pyramid_gz_kb": round(pyr_size / 1024, 2),
        "chunk_count": len(prefix_size),
        "chunk_max_gz_kb": round(max(prefix_size.values()) / 1024, 2) if prefix_size else 0,
        "chunk_p95_gz_kb": round(sorted(prefix_size.values())[int(0.95 * len(prefix_size))] / 1024, 2) if prefix_size else 0,
        "lookups": {},
    }
    for label, pts in [("kigali", kigali), ("rural", rural)]:
        for acc in [20, 100, 500]:
            key = f"{label}_acc{acc}"
            report["lookups"][key] = measure(pts, acc)
            print(key, report["lookups"][key], flush=True)
    max_lookup = max(v["max"] for v in report["lookups"].values()) if report["lookups"] else 0
    report["max_lookup_kb"] = max_lookup
    report["exceeds_150kb"] = max_lookup > 150
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if report["exceeds_150kb"]:
        print("WARN: max lookup > 150 KB — split dense gh4 into gh5 needed")
    print("DONE size_benchmark")

if __name__ == "__main__":
    main()
