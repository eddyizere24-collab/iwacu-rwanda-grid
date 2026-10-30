#!/usr/bin/env python3
"""Per-district validation: PIP truth, exact-length noise, SEED-TEST."""
from __future__ import annotations
import argparse, json, math, random, collections, sys
from pathlib import Path
# allow importing sibling module in scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_lib import (
    SEED_TUNE, SEED_TEST, NOISES, LAT_M, lng_m,
    load_cells, locate_gauss, random_interior, load_national_prep,
)
from shapely.geometry import shape, Point
from shapely.validation import make_valid

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--district", required=True)
    ap.add_argument("--seed-test", type=int, default=SEED_TEST)
    ap.add_argument("--seed-tune", type=int, default=SEED_TUNE)
    ap.add_argument("--points", type=int, default=500)
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--chunks", default="artifacts/algo_out/chunks_gh4")
    ap.add_argument("--national", default="data/rwanda_national.geojson")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["test", "tune"], default="test")
    args = ap.parse_args()
    seed = args.seed_test if args.mode == "test" else args.seed_tune
    rng = random.Random(seed)
    with open(args.geojson) as f:
        fc = json.load(f)
    dfeats = [feat for feat in fc["features"] if str(feat["properties"]["district_id"]) == args.district]
    del fc
    villages = []
    for feat in dfeats:
        poly = shape(feat["geometry"])
        if not poly.is_valid:
            poly = make_valid(poly)
        villages.append((str(feat["properties"]["village_id"]), poly))
    national_prep = load_national_prep(args.national)
    cell_map, meta = load_cells(Path(args.chunks), args.district)
    n_interior = int(args.points * 0.8)
    n_border = args.points - n_interior
    samples, picks = [], villages[:]
    rng.shuffle(picks)
    for vid, poly in picks:
        if len([s for s in samples if s[3] == "interior"]) >= n_interior:
            break
        lat, lon = random_interior(poly, rng)
        samples.append((vid, lat, lon, "interior"))
    for vid, poly in picks:
        if len([s for s in samples if s[3] == "border"]) >= n_border:
            break
        try:
            b = poly.boundary
            pt = b.interpolate(rng.random(), normalized=True)
            c = poly.centroid
            dx, dy = c.x - pt.x, c.y - pt.y
            norm = math.hypot(dx, dy) or 1
            nlat = pt.y + (dy / norm) * (25 / LAT_M)
            nlon = pt.x + (dx / norm) * (25 / lng_m(pt.y))
            if poly.covers(Point(nlon, nlat)):
                samples.append((vid, nlat, nlon, "border"))
        except Exception:
            continue
    stats = {r: {"interior": collections.Counter(), "border": collections.Counter(), "all": collections.Counter()} for r in NOISES}
    chosen_ok = {r: collections.Counter() for r in NOISES}
    calib = []
    for true_vid, lat0, lon0, kind in samples:
        true_meta = meta.get(true_vid) or {}
        for r in NOISES:
            if r == 0:
                lat, lon = lat0, lon0
            else:
                bearing = rng.random() * 2 * math.pi
                lat = lat0 + (r * math.cos(bearing)) / LAT_M
                lon = lon0 + (r * math.sin(bearing)) / lng_m(lat0)
            gt = None
            for vid, poly in villages:
                if poly.covers(Point(lon, lat)):
                    gt = vid
                    break
            if gt is None:
                gt = true_vid
            res = locate_gauss(lat, lon, max(r, 5), cell_map, meta, national_prep)
            top1 = res["top"][0][0] if res["top"] else None
            hit = top1 == gt
            top3_hit = gt in [t[0] for t in res["top"][:3]]
            stats[r][kind]["n"] += 1
            stats[r]["all"]["n"] += 1
            if hit:
                stats[r][kind]["top1"] += 1
                stats[r]["all"]["top1"] += 1
            if top3_hit:
                stats[r][kind]["top3"] += 1
                stats[r]["all"]["top3"] += 1
            ok = False
            if res["finestLevel"] == "village":
                ok = top1 == gt
            elif res["finestLevel"] == "cell":
                ok = res["chosen_id"] == true_meta.get("c")
            elif res["finestLevel"] == "sector":
                ok = res["chosen_id"] == true_meta.get("s")
            elif res["finestLevel"] == "district":
                ok = res["chosen_id"] == args.district
            elif res["finestLevel"] == "province":
                ok = True
            chosen_ok[r]["n"] += 1
            if ok:
                chosen_ok[r]["ok"] += 1
            calib.append((res.get("Pv_top1", 0), 1 if hit else 0))

    def rate(c, k):
        n = c.get("n") or 1
        return round(100 * c.get(k, 0) / n, 2)

    metrics = {
        "district_id": args.district,
        "seed": seed,
        "mode": args.mode,
        "n_samples": len(samples),
        "n_interior": len([s for s in samples if s[3] == "interior"]),
        "n_border": len([s for s in samples if s[3] == "border"]),
        "by_noise": {},
        "chosen_correct_pct": {},
        "protocol": "PIP truth, exact-length offset, Gaussian locate",
    }
    for r in NOISES:
        metrics["by_noise"][str(r)] = {
            "all_top1": rate(stats[r]["all"], "top1"),
            "all_top3": rate(stats[r]["all"], "top3"),
            "interior_top1": rate(stats[r]["interior"], "top1"),
            "border_top1": rate(stats[r]["border"], "top1"),
            "n": stats[r]["all"]["n"],
        }
        metrics["chosen_correct_pct"][str(r)] = rate(chosen_ok[r], "ok") if chosen_ok[r]["n"] else 0
    bins = [[] for _ in range(10)]
    for p, h in calib:
        bins[min(9, int(p * 10))].append(h)
    ece, n_tot = 0.0, len(calib) or 1
    for i, b in enumerate(bins):
        if not b:
            continue
        ece += (len(b) / n_tot) * abs(sum(b) / len(b) - (i + 0.5) / 10)
    metrics["ece_approx"] = round(ece, 4)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(metrics, open(args.out, "w"), indent=2)
    print(json.dumps(metrics, indent=2))

if __name__ == "__main__":
    main()
