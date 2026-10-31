#!/usr/bin/env python3
"""Independent Kivu border check vs Natural Earth; regenerate test points >=300m from both lines."""
from __future__ import annotations
import argparse, json, math, random, urllib.request
from pathlib import Path
from shapely.geometry import shape, Point, box
from shapely.validation import make_valid
from shapely.prepared import prep
from shapely.ops import nearest_points

ADM0_URL = "https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/gbOpen/RWA/ADM0/geoBoundaries-RWA-ADM0.geojson"
NE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
KIVU_BBOX = (28.75, -2.60, 29.45, -1.55)
MARGIN_M = 300.0
LAT_M = 110574.0

def lng_m(lat):
    return 111320.0 * max(0.3, abs(math.cos(math.radians(lat))))

def dist_m_to_boundary(pt, geom):
    return pt.distance(geom.boundary) * LAT_M

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adm0", default="data/geoBoundaries-RWA-ADM0.geojson")
    ap.add_argument("--national", default="data/rwanda_national.geojson")
    ap.add_argument("--out-csv", default="data/kivu_test_points.csv")
    ap.add_argument("--out-report", default="data/kivu_check_report.json")
    args = ap.parse_args()
    if not Path(args.adm0).exists():
        with urllib.request.urlopen(ADM0_URL, timeout=90) as r:
            Path(args.adm0).write_bytes(r.read())
    adm0 = shape(json.loads(Path(args.adm0).read_text())["features"][0]["geometry"])
    if not adm0.is_valid:
        adm0 = make_valid(adm0)
    print("Downloading Natural Earth admin0...", flush=True)
    with urllib.request.urlopen(NE_URL, timeout=120) as r:
        ne = json.loads(r.read().decode())
    ne_rwa = None
    for f in ne["features"]:
        props = f.get("properties") or {}
        name = (props.get("ADMIN") or props.get("NAME") or props.get("name") or "").upper()
        if name == "RWANDA":
            ne_rwa = shape(f["geometry"]); break
    if ne_rwa is None:
        raise SystemExit("Rwanda not found in Natural Earth")
    if not ne_rwa.is_valid:
        ne_rwa = make_valid(ne_rwa)
    rng = random.Random(20261030)
    kivu = box(*KIVU_BBOX)
    adm0_b = adm0.boundary.intersection(kivu.buffer(0.05))
    ne_b = ne_rwa.boundary.intersection(kivu.buffer(0.05))
    deviations = []
    for _ in range(400):
        lat = rng.uniform(KIVU_BBOX[1], KIVU_BBOX[3])
        lon = rng.uniform(KIVU_BBOX[0], KIVU_BBOX[2])
        pt = Point(lon, lat)
        try:
            p1 = nearest_points(pt, adm0_b)[1]
            p2 = nearest_points(p1, ne_b)[1]
            deviations.append(p1.distance(p2) * LAT_M)
        except Exception:
            continue
    max_dev = max(deviations) if deviations else -1
    mean_dev = sum(deviations) / len(deviations) if deviations else -1
    print(f"Kivu deviation max_m={max_dev:.1f} mean_m={mean_dev:.1f} n={len(deviations)}", flush=True)
    prep_adm0, prep_ne = prep(adm0), prep(ne_rwa)
    inside, outside, ambiguous = [], [], []
    for _ in range(20000):
        lat = rng.uniform(KIVU_BBOX[1], KIVU_BBOX[3])
        lon = rng.uniform(KIVU_BBOX[0], KIVU_BBOX[2])
        pt = Point(lon, lat)
        d_a, d_n = dist_m_to_boundary(pt, adm0), dist_m_to_boundary(pt, ne_rwa)
        if d_a < MARGIN_M or d_n < MARGIN_M:
            if len(ambiguous) < 30:
                ambiguous.append((lat, lon, "AMBIGUOUS", f"d_adm0={d_a:.0f} d_ne={d_n:.0f}"))
            continue
        a_in, n_in = prep_adm0.contains(pt), prep_ne.contains(pt)
        if a_in and n_in and len(inside) < 25:
            inside.append((lat, lon, "INSIDE", f"both_contain d_adm0={d_a:.0f}"))
        elif (not a_in) and (not n_in) and len(outside) < 25:
            outside.append((lat, lon, "OUTSIDE", f"both_exclude d_adm0={d_a:.0f}"))
        if len(inside) >= 25 and len(outside) >= 25:
            break
    ring_counts = {}
    if Path(args.national).exists():
        national = shape(json.loads(Path(args.national).read_text())["features"][0]["geometry"])
        if not national.is_valid:
            national = make_valid(national)
        prep_nat = prep(national)
        for dist_m in [100, 500, 1000, 2000]:
            flagged_inside, samples = 0, 0
            for _ in range(200):
                try:
                    bpt = national.boundary.interpolate(rng.random(), normalized=True)
                    ang = rng.random() * 2 * math.pi
                    la = bpt.y + (dist_m * math.cos(ang)) / LAT_M
                    lo = bpt.x + (dist_m * math.sin(ang)) / lng_m(bpt.y)
                    samples += 1
                    if prep_nat.contains(Point(lo, la)):
                        flagged_inside += 1
                except Exception:
                    continue
            ring_counts[str(dist_m)] = {"samples": samples, "flagged_inside": flagged_inside}
            print(f"outside_ring {dist_m}m: flagged_inside={flagged_inside}/{samples}", flush=True)
    neighbors = [(-2.85, 29.25, "OUTSIDE", "Burundi_south"), (-2.20, 30.95, "OUTSIDE", "Tanzania_east"),
                 (-1.02, 30.05, "OUTSIDE", "Uganda_north"), (-1.55, 28.65, "OUTSIDE", "DRC_northwest")]
    rows = ["lat,lng,expected,why"]
    for row in inside + outside + neighbors:
        rows.append(f"{row[0]:.6f},{row[1]:.6f},{row[2]},{row[3]}")
    Path(args.out_csv).write_text("\n".join(rows) + "\n")
    report = {
        "second_source": "Natural Earth 50m admin_0",
        "second_source_url": NE_URL,
        "primary_source": ADM0_URL,
        "kivu_max_deviation_m": round(max_dev, 1),
        "kivu_mean_deviation_m": round(mean_dev, 1),
        "margin_m": MARGIN_M,
        "inside_points": len(inside),
        "outside_points": len(outside),
        "ambiguous_points_sample": len(ambiguous),
        "outside_ring_flagged_inside": ring_counts,
    }
    Path(args.out_report).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print("DONE kivu_check")

if __name__ == "__main__":
    main()
