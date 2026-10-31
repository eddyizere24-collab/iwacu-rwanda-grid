#!/usr/bin/env python3
"""A5 invariants: missing=0; pure mismatch<=0.1%; pure r0>=99.9% all Q; interior r0>=99%."""
from __future__ import annotations
import argparse, json, gzip, random, sys
from pathlib import Path
from shapely.geometry import shape, Point
from shapely.validation import make_valid
from shapely.strtree import STRtree
import pygeohash as pgh

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--chunks", default="artifacts/exact_out/chunks_gh4")
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

    pure, shares = {}, {}
    for p in Path(args.chunks).glob("*.json.gz"):
        with gzip.open(p, "rt") as f:
            ch = json.load(f)
        for c in ch["cells"]:
            shares[c["g"]] = c
            if c.get("pure"):
                pure[c["g"]] = str(c["t"][0]["v"])

    rng = random.Random(20261030)
    miss = n_int = 0
    for i, g in enumerate(vgeoms):
        minx, miny, maxx, maxy = g.bounds
        for _ in range(max(1, 100000 // max(1, len(vgeoms)))):
            x = rng.uniform(minx, maxx)
            y = rng.uniform(miny, maxy)
            if not g.covers(Point(x, y)):
                continue
            n_int += 1
            found = any(pgh.encode(y, x, p) in shares for p in (9, 8, 7))
            if not found:
                miss += 1
            if n_int >= 100000:
                break
        if n_int >= 100000:
            break

    ghs = list(pure.keys())
    rng.shuffle(ghs)
    ok = mis = 0
    for gh in ghs[:800]:
        assigned = pure[gh]
        lat, lon, lat_err, lon_err = pgh.decode_exactly(gh)
        for _ in range(20):
            x = rng.uniform(lon - lon_err, lon + lon_err)
            y = rng.uniform(lat - lat_err, lat + lat_err)
            t = pip(x, y)
            if t is None:
                continue
            if t != assigned:
                mis += 1
            else:
                ok += 1

    by_q = {q: {"n": 0, "hit": 0} for q in ("Q1", "Q2", "Q3", "Q4")}
    pure_hits = {q: {"n": 0, "hit": 0} for q in ("Q1", "Q2", "Q3", "Q4")}
    for i, g in enumerate(vgeoms):
        minx, miny, maxx, maxy = g.bounds
        for _ in range(5):
            x = rng.uniform(minx, maxx)
            y = rng.uniform(miny, maxy)
            if not g.covers(Point(x, y)):
                continue
            q = quartile(areas[i])
            pred = None
            pure_cell = False
            for p in (9, 8, 7):
                gh = pgh.encode(y, x, p)
                if gh in shares:
                    pred = str(shares[gh]["t"][0]["v"])
                    pure_cell = bool(shares[gh].get("pure"))
                    break
            by_q[q]["n"] += 1
            if pred == vids[i]:
                by_q[q]["hit"] += 1
            if pure_cell:
                pure_hits[q]["n"] += 1
                if pred == vids[i]:
                    pure_hits[q]["hit"] += 1

    def pct(h, n):
        return round(100 * h / n, 3) if n else None

    mismatch_pct = 100 * mis / max(1, ok + mis)
    report = {
        "a_missing_cells": miss,
        "a_interior_tested": n_int,
        "b_pure_ok": ok,
        "b_pure_mismatch": mis,
        "b_pure_mismatch_pct": round(mismatch_pct, 4),
        "c_pure_r0_by_quartile": {q: pct(pure_hits[q]["hit"], pure_hits[q]["n"]) for q in pure_hits},
        "d_interior_r0_by_quartile": {q: pct(by_q[q]["hit"], by_q[q]["n"]) for q in by_q},
        "d_interior_r0_overall": pct(sum(by_q[q]["hit"] for q in by_q), sum(by_q[q]["n"] for q in by_q)),
    }
    report["pass_a"] = miss == 0
    report["pass_b"] = mismatch_pct <= 0.1  # matches 99.9% purity rule
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
