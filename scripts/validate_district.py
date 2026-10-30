#!/usr/bin/env python3
"""Per-district validation. SEED-TEST=20261030 held out. Full PIP in CI when geojson present."""
import argparse, json
from pathlib import Path
SEED_TEST = 20261030
SEED_TUNE = 424242
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--district", required=True)
    ap.add_argument("--seed-test", type=int, default=SEED_TEST)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    metrics = {
        "district_id": args.district,
        "seed": args.seed_test,
        "seed_tune": SEED_TUNE,
        "protocol": "500 pts (400 interior + 100 border), exact-length offset, PIP truth",
        "status": "PENDING_FULL_PIP",
        "criteria": {k: "UNVERIFIED" for k in ["A1","A2","A3","A4","A5","A6","A7"]},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(metrics, open(args.out, "w"), indent=2)
    print("wrote", args.out)
if __name__ == "__main__":
    main()
