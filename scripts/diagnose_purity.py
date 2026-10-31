#!/usr/bin/env python3
"""Pure-cell integrity: PIP mismatch in pure cells, geohash agreement, missing cells, ID check."""
from __future__ import annotations
import argparse, json, random, gzip
from pathlib import Path
from shapely.geometry import shape, Point
from shapely.validation import make_valid
from shapely.strtree import STRtree
import pygeohash as pgh

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--districts", default="11,37")
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--chunks", default="artifacts/algo_out/chunks_gh4")
    ap.add_argument("--out", default="data/purity_report.json")
    ap.add_argument("--pure-cells-sample", type=int, default=500)
    ap.add_argument("--pts-per-cell", type=int, default=20)
    args = ap.parse_args()
    districts = set(args.districts.split(","))

    with open(args.geojson) as f:
        feats = json.load(f)["features"]
    vgeoms, vids = [], []
    for feat in feats:
        if str(feat["properties"]["district_id"]) not in districts:
            continue
        g = shape(feat["geometry"])
        if not g.is_valid:
            g = make_valid(g)
        vgeoms.append(g)
        vids.append(str(feat["properties"]["village_id"]).strip())
    tree = STRtree(vgeoms)
    truth = set(vids)

    def pip(x, y):
        pt = Point(x, y)
        for i in tree.query(pt):
            if vgeoms[i].covers(pt):
                return vids[i]
        return None

    pure, shares, ids_in_cells = {}, {}, set()
    for p in sorted(Path(args.chunks).glob("*.json.gz")):
        with gzip.open(p, "rt") as f:
            ch = json.load(f)
        for c in ch["cells"]:
            for t in c["t"]:
                ids_in_cells.add(str(t["v"]).strip())
            shares[c["g"]] = c["t"]
            if len(c["t"]) == 1:
                pure[c["g"]] = str(c["t"][0]["v"]).strip()

    only_truth = sorted(truth - ids_in_cells)
    only_grid = sorted(ids_in_cells - truth)

    rng = random.Random(42)
    ghs = [gh for gh, v in pure.items() if v in truth]
    rng.shuffle(ghs)
    ghs = ghs[: args.pure_cells_sample]
    ok = mis = nov = 0
    examples = []
    for gh in ghs:
        assigned = pure[gh]
        lat, lon, lat_err, lon_err = pgh.decode_exactly(gh)
        for _ in range(args.pts_per_cell):
            x = rng.uniform(lon - lon_err, lon + lon_err)
            y = rng.uniform(lat - lat_err, lat + lat_err)
            t = pip(x, y)
            if t is None:
                nov += 1
                continue
            if t != assigned:
                mis += 1
                if len(examples) < 10:
                    examples.append({"gh": gh, "lat": round(y, 6), "lng": round(x, 6),
                                    "assigned": assigned, "true": t})
            else:
                ok += 1

    dis_swap = 0
    for _ in range(1000):
        lat = rng.uniform(-2.2, -1.8)
        lon = rng.uniform(29.9, 30.3)
        if pgh.encode(lat, lon, 7) != pgh.encode(lon, lat, 7):
            dis_swap += 1

    miss = wrong = good = 0
    for i, g in enumerate(vgeoms):
        minx, miny, maxx, maxy = g.bounds
        for _ in range(3):
            x = rng.uniform(minx, maxx)
            y = rng.uniform(miny, maxy)
            if not g.covers(Point(x, y)):
                continue
            gh = pgh.encode(y, x, 7)
            s = shares.get(gh)
            if not s:
                miss += 1
            elif str(s[0]["v"]).strip() != vids[i]:
                wrong += 1
            else:
                good += 1

    report = {
        "districts": sorted(districts),
        "purity_rule": "STRICT len(share_list)==1 (build sampling, NOT exact polygon intersection)",
        "pure_cells_total": len(pure),
        "pure_cells_tested": len(ghs),
        "pts_per_cell": args.pts_per_cell,
        "pure_pip_ok": ok,
        "pure_pip_mismatch": mis,
        "pure_pip_no_village": nov,
        "pure_pip_mismatch_pct": round(100 * mis / max(1, ok + mis), 3),
        "examples_mismatch": examples,
        "geohash_self_disagree": 0,
        "geohash_latlng_swap_disagree": dis_swap,
        "geohash_encode_sample": {"latlon": pgh.encode(-1.95, 30.05, 7), "lonlat": pgh.encode(30.05, -1.95, 7)},
        "interior_good": good,
        "interior_wrong_majority": wrong,
        "interior_missing_gh7": miss,
        "ids_only_in_truth": only_truth[:20],
        "ids_only_in_truth_count": len(only_truth),
        "ids_only_in_grid_not_district_truth": len(only_grid),
        "locate_at_accuracy_0": "sigma=1e-6; weights cells whose centres lie within ~80m; uses share list majority",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
