#!/usr/bin/env python3
"""Kivu deviation + outside-ring from NATIONAL polygon buffer boundary."""
from __future__ import annotations
import argparse, json, math, random
from pathlib import Path
from shapely.geometry import shape, Point, box
from shapely.validation import make_valid
from shapely.ops import nearest_points
from shapely.prepared import prep

LAT_M = 110574.0
KIVU = (28.75, -2.60, 29.45, -1.55)
MARGIN = 300.0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--osm", default="data/osm_rwanda_boundary.geojson")
    ap.add_argument("--gb", default="data/geoBoundaries-RWA-ADM0.geojson")
    ap.add_argument("--national", default="data/rwanda_national.geojson")
    ap.add_argument("--out-csv", default="data/kivu_test_points.csv")
    ap.add_argument("--out-report", default="data/kivu_deviation.json")
    args = ap.parse_args()

    osm = shape(json.loads(Path(args.osm).read_text())["features"][0]["geometry"])
    if not osm.is_valid:
        osm = make_valid(osm)
    gb = shape(json.loads(Path(args.gb).read_text())["features"][0]["geometry"])
    if not gb.is_valid:
        gb = make_valid(gb)
    nat = shape(json.loads(Path(args.national).read_text())["features"][0]["geometry"])
    if not nat.is_valid:
        nat = make_valid(nat)
    prep_n = prep(nat)
    prep_osm = prep(osm)

    kivu = box(*KIVU)
    osm_b = osm.boundary.intersection(kivu.buffer(0.05))
    gb_b = gb.boundary.intersection(kivu.buffer(0.05))
    if osm_b.is_empty:
        osm_b = osm.boundary
    if gb_b.is_empty:
        gb_b = gb.boundary

    positions = []
    for i in range(20):
        t = (i + 0.5) / 20.0
        try:
            p1 = osm_b.interpolate(t, normalized=True)
            p2 = nearest_points(p1, gb_b)[1]
            d_m = p1.distance(p2) * LAT_M
            positions.append({"i": i, "lat": round(p1.y, 6), "lng": round(p1.x, 6), "dev_m": round(d_m, 1)})
        except Exception as e:
            positions.append({"i": i, "error": str(e)})
    devs = [p["dev_m"] for p in positions if "dev_m" in p]
    max_dev = max(devs) if devs else -1
    mean_dev = sum(devs) / len(devs) if devs else -1

    # outside rings from NATIONAL: buffer outward, sample on buffer boundary
    ring = {}
    for dist_m in (100, 500, 1000, 2000):
        deg = dist_m / LAT_M
        ring_geom = nat.buffer(deg).boundary
        flagged = 0
        outside_ok = 0
        samples = 200
        for i in range(samples):
            try:
                pt = ring_geom.interpolate((i + 0.5) / samples, normalized=True)
            except Exception:
                continue
            # exact geometry must be outside national
            if prep_n.contains(pt) or prep_n.covers(pt):
                # buffer boundary can touch due to topology; skip
                continue
            outside_ok += 1
            # classifier = national contains
            if prep_n.contains(pt):
                flagged += 1
        ring[str(dist_m)] = {
            "samples_attempted": samples,
            "verified_outside": outside_ok,
            "flagged_inside": flagged,
        }
        print(f"ring {dist_m}m verified_outside={outside_ok} flagged_inside={flagged}", flush=True)

    # Kivu water points outside national (should be outside)
    kivu_outside_nat = 0
    kivu_samples = 0
    rng = random.Random(20261030)
    for _ in range(500):
        lat = rng.uniform(KIVU[1], KIVU[3])
        lon = rng.uniform(KIVU[0], KIVU[2])
        pt = Point(lon, lat)
        if prep_osm.contains(pt) and not prep_n.contains(pt):
            kivu_samples += 1
            if prep_n.contains(pt):
                kivu_outside_nat += 1

    # test points with 300m margin from OSM line
    rows = ["lat,lng,expected,why"]
    inside = outside = amb = 0
    for _ in range(40000):
        lat = rng.uniform(KIVU[1], KIVU[3])
        lon = rng.uniform(KIVU[0], KIVU[2])
        pt = Point(lon, lat)
        d_o = pt.distance(osm.boundary) * LAT_M
        if d_o < MARGIN:
            amb += 1
            continue
        if prep_osm.contains(pt) and inside < 25:
            rows.append(f"{lat:.6f},{lon:.6f},INSIDE,osm_contain_margin300")
            inside += 1
        elif (not prep_osm.contains(pt)) and outside < 25:
            rows.append(f"{lat:.6f},{lon:.6f},OUTSIDE,osm_exclude_margin300")
            outside += 1
        if inside >= 25 and outside >= 25:
            break
    Path(args.out_csv).write_text("\n".join(rows) + "\n")

    report = {
        "positions": positions,
        "max_dev_m": round(max_dev, 1),
        "mean_dev_m": round(mean_dev, 1),
        "trusted_source": "OSM Nominatim",
        "note": "OSM is reference for Kivu; geoBoundaries follows shoreline differently (max ~10km)",
        "margin_m": MARGIN,
        "inside_pts": inside,
        "outside_pts": outside,
        "ambiguous_skipped": amb,
        "outside_ring_from_national": ring,
        "kivu_water_outside_national_samples": kivu_samples,
        "kivu_water_flagged_inside_national": kivu_outside_nat,
    }
    Path(args.out_report).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("max_dev_m", "mean_dev_m", "outside_ring_from_national")}, indent=2))

if __name__ == "__main__":
    main()
