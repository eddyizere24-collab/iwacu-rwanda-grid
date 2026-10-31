#!/usr/bin/env python3
"""Invariants a-d via shipped binary index (root + gh6) with longest-prefix resolution."""
from __future__ import annotations
import argparse, json, random, sys
from pathlib import Path
from shapely.geometry import shape, Point
from shapely.validation import make_valid
from shapely.strtree import STRtree
import pygeohash as pgh
from grid_codec import ShippedIndex

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--out-dir", default="artifacts/exact_out")
    ap.add_argument("--districts", default="11,12,13,37")
    ap.add_argument("--out", default="data/invariants_report.json")
    args = ap.parse_args()
    districts = set(args.districts.split(","))

    with open(args.geojson) as f:
        feats = [ft for ft in json.load(f)["features"] if str(ft["properties"]["district_id"]) in districts]
    vgeoms, vids, areas = [], [], []
    for ft in feats:
        g = shape(ft["geometry"])
        if not g.is_valid:
            g = make_valid(g)
        vgeoms.append(g)
        vids.append(str(ft["properties"]["village_id"]).strip())
        areas.append(g.area)
    tree = STRtree(vgeoms)
    qs = sorted(areas)

    def quartile(a):
        if a <= qs[len(qs) // 4]:
            return "Q1"
        if a <= qs[len(qs) // 2]:
            return "Q2"
        if a <= qs[3 * len(qs) // 4]:
            return "Q3"
        return "Q4"

    def pip(x, y):
        pt = Point(x, y)
        for i in tree.query(pt):
            if vgeoms[i].covers(pt):
                return vids[i]
        return None

    idx = ShippedIndex(Path(args.out_dir))
    # preload all gh6 for pure-cell sampling
    for p in (Path(args.out_dir) / "gh6").glob("*.bin.gz"):
        idx._ensure_gh6(p.stem)

    pure_keys = [gh for gh, info in idx.all.items() if info["pure"]]
    rng = random.Random(20261030)

    # (a) missing among interior points
    miss = n_int = 0
    miss_ex = []
    for i, g in enumerate(vgeoms):
        minx, miny, maxx, maxy = g.bounds
        for _ in range(max(1, 100000 // max(1, len(vgeoms)))):
            x = rng.uniform(minx, maxx)
            y = rng.uniform(miny, maxy)
            if not g.covers(Point(x, y)):
                continue
            n_int += 1
            key, info, gh9 = idx.resolve(y, x)
            if key is None:
                miss += 1
                if len(miss_ex) < 10:
                    miss_ex.append({"lat": round(y, 6), "lng": round(x, 6), "gh9": gh9,
                                    "expected": vids[i], "got": None})
            if n_int >= 100000:
                break
        if n_int >= 100000:
            break

    # (b) pure-cell mismatch: sample points in pure cell bbox
    ok = mis = 0
    mis_ex = []
    rng.shuffle(pure_keys)
    for gh in pure_keys[:800]:
        assigned = idx.all[gh]["shares"][0][0]
        lat, lon, lat_err, lon_err = pgh.decode_exactly(gh)
        for _ in range(20):
            x = rng.uniform(lon - lon_err, lon + lon_err)
            y = rng.uniform(lat - lat_err, lat + lat_err)
            t = pip(x, y)
            if t is None:
                continue
            key, info, _ = idx.resolve(y, x)
            got = info["shares"][0][0] if info else None
            # pure-cell invariant: PIP truth vs cell's assigned village
            if t != assigned:
                # point may fall outside the pure village in cell bbox (neighbor)
                # only count if resolve also points to this pure cell's village wrongly
                pass
            if t != assigned:
                mis += 1
                if len(mis_ex) < 10:
                    mis_ex.append({"cell": gh, "lat": round(y, 6), "lng": round(x, 6),
                                   "expected": t, "got_assigned": assigned, "resolved": got})
            else:
                ok += 1

    # (c)(d) top1 via longest-prefix resolve
    by_q = {q: {"n": 0, "hit": 0} for q in ("Q1", "Q2", "Q3", "Q4")}
    pure_hits = {q: {"n": 0, "hit": 0} for q in ("Q1", "Q2", "Q3", "Q4")}
    fail_c = []
    fail_d = []
    for i, g in enumerate(vgeoms):
        minx, miny, maxx, maxy = g.bounds
        for _ in range(5):
            x = rng.uniform(minx, maxx)
            y = rng.uniform(miny, maxy)
            if not g.covers(Point(x, y)):
                continue
            q = quartile(areas[i])
            key, info, gh9 = idx.resolve(y, x)
            pred = info["shares"][0][0] if info else None
            pure_cell = bool(info and info["pure"]) if info else False
            by_q[q]["n"] += 1
            if pred == vids[i]:
                by_q[q]["hit"] += 1
            else:
                if len(fail_d) < 10:
                    fail_d.append({"lat": round(y, 6), "lng": round(x, 6), "gh9": gh9,
                                   "key": key, "expected": vids[i], "got": pred})
            if pure_cell:
                pure_hits[q]["n"] += 1
                if pred == vids[i]:
                    pure_hits[q]["hit"] += 1
                elif len(fail_c) < 10:
                    fail_c.append({"lat": round(y, 6), "lng": round(x, 6), "key": key,
                                   "expected": vids[i], "got": pred})

    def pct(h, n):
        return round(100 * h / n, 3) if n else None

    mismatch_pct = 100 * mis / max(1, ok + mis)
    report = {
        "decoder": "shipped_binary_longest_prefix",
        "a_missing_cells": miss,
        "a_interior_tested": n_int,
        "a_examples": miss_ex,
        "b_pure_ok": ok,
        "b_pure_mismatch": mis,
        "b_pure_mismatch_pct": round(mismatch_pct, 4),
        "b_examples": mis_ex,
        "c_pure_r0_by_quartile": {q: pct(pure_hits[q]["hit"], pure_hits[q]["n"]) for q in pure_hits},
        "c_examples": fail_c,
        "d_interior_r0_by_quartile": {q: pct(by_q[q]["hit"], by_q[q]["n"]) for q in by_q},
        "d_interior_r0_overall": pct(sum(by_q[q]["hit"] for q in by_q), sum(by_q[q]["n"] for q in by_q)),
        "d_examples": fail_d,
    }
    report["pass_a"] = miss == 0
    report["pass_b"] = mismatch_pct <= 0.1
    report["pass_c"] = all(
        (pure_hits[q]["hit"] / pure_hits[q]["n"] if pure_hits[q]["n"] else 1) >= 0.999 for q in pure_hits
    )
    report["pass_d"] = (report["d_interior_r0_overall"] or 0) >= 99.0
    report["all_pass"] = all(report[k] for k in ("pass_a", "pass_b", "pass_c", "pass_d"))
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not report["all_pass"]:
        sys.exit(1)

if __name__ == "__main__":
    main()
