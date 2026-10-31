#!/usr/bin/env python3
"""OSM vs geoBoundaries deviation along Kivu + regenerate test points (300m margin)."""
from __future__ import annotations
import argparse, json, math, random
from pathlib import Path
from shapely.geometry import shape, Point, box, LineString
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
    ap.add_argument("--out-report", default="data/kivu_deviation_report.json")
    args = ap.parse_args()

    osm = shape(json.loads(Path(args.osm).read_text())["features"][0]["geometry"])
    if not osm.is_valid:
        osm = make_valid(osm)
    gb = shape(json.loads(Path(args.gb).read_text())["features"][0]["geometry"])
    if not gb.is_valid:
        gb = make_valid(gb)

    kivu = box(*KIVU)
    osm_b = osm.boundary.intersection(kivu.buffer(0.05))
    gb_b = gb.boundary.intersection(kivu.buffer(0.05))

    # 20 evenly spaced samples along OSM boundary in Kivu
    positions = []
    if osm_b.is_empty:
        osm_b = osm.boundary
    length = osm_b.length if not osm_b.is_empty else 0
    for i in range(20):
        t = (i + 0.5) / 20.0
        try:
            p1 = osm_b.interpolate(t, normalized=True)
            p2 = nearest_points(p1, gb_b)[1]
            d_m = p1.distance(p2) * LAT_M
            positions.append({"i": i, "lat": round(p1.y, 6), "lng": round(p1.x, 6),
                              "dev_m": round(d_m, 1)})
        except Exception as e:
            positions.append({"i": i, "error": str(e)})
    devs = [p["dev_m"] for p in positions if "dev_m" in p]
    max_dev = max(devs) if devs else -1
    mean_dev = sum(devs) / len(devs) if devs else -1
    print(f"max_dev_m={max_dev} mean_dev_m={mean_dev}", flush=True)

    trusted = "OSM Nominatim" if max_dev > 1000 else "both_agree_within_1km"
    note = (
        "Trust OSM for Kivu shoreline: geoBoundaries ADM0 often truncates lake; "
        "OSM includes Rwanda water share consistent with ~1009 km2 added."
        if max_dev > 1000 else "Lines agree within 1 km."
    )

    rng = random.Random(20261030)
    prep_osm, prep_gb = prep(osm), prep(gb)
    rows = ["lat,lng,expected,why"]
    inside = outside = amb = 0
    for _ in range(30000):
        lat = rng.uniform(KIVU[1], KIVU[3])
        lon = rng.uniform(KIVU[0], KIVU[2])
        pt = Point(lon, lat)
        d_o = pt.distance(osm.boundary) * LAT_M
        d_g = pt.distance(gb.boundary) * LAT_M
        if d_o < MARGIN or d_g < MARGIN:
            amb += 1
            continue
        o_in, g_in = prep_osm.contains(pt), prep_gb.contains(pt)
        if o_in and g_in and inside < 25:
            rows.append(f"{lat:.6f},{lon:.6f},INSIDE,both_contain")
            inside += 1
        elif (not o_in) and (not g_in) and outside < 25:
            rows.append(f"{lat:.6f},{lon:.6f},OUTSIDE,both_exclude")
            outside += 1
        if inside >= 25 and outside >= 25:
            break

    ring = {}
    if Path(args.national).exists():
        nat = shape(json.loads(Path(args.national).read_text())["features"][0]["geometry"])
        if not nat.is_valid:
            nat = make_valid(nat)
        prep_n = prep(nat)
        for dist_m in (100, 500, 1000, 2000):
            flagged = samples = 0
            for _ in range(200):
                try:
                    bpt = nat.boundary.interpolate(rng.random(), normalized=True)
                    ang = rng.random() * 2 * math.pi
                    la = bpt.y + (dist_m * math.cos(ang)) / LAT_M
                    lo = bpt.x + (dist_m * math.sin(ang)) / (111320 * max(0.3, abs(math.cos(math.radians(bpt.y)))))
                    samples += 1
                    if prep_n.contains(Point(lo, la)):
                        flagged += 1
                except Exception:
                    continue
            ring[str(dist_m)] = {"samples": samples, "flagged_inside": flagged}
            print(f"ring {dist_m}m flagged={flagged}/{samples}", flush=True)

    Path(args.out_csv).write_text("\n".join(rows) + "\n")
    report = {
        "positions": positions,
        "max_dev_m": round(max_dev, 1),
        "mean_dev_m": round(mean_dev, 1),
        "trusted_source": trusted,
        "note": note,
        "inside_pts": inside,
        "outside_pts": outside,
        "ambiguous_skipped": amb,
        "outside_ring_flagged_inside": ring,
        "margin_m": MARGIN,
    }
    Path(args.out_report).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("max_dev_m", "mean_dev_m", "trusted_source", "outside_ring_flagged_inside")}, indent=2))

if __name__ == "__main__":
    main()
