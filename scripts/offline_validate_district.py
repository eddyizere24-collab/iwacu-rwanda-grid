#!/usr/bin/env python3
"""Offline validation harness for one district (no DB).

Noise: exact-length offset at random bearing.
1 deg lat = 110574 m; 1 deg lng = 111320 * cos(lat) m.
CHANGED 2026-11-01 GROK: see docs/HANDOFF.md offline design
"""
from __future__ import annotations
import argparse, json, math, random
from pathlib import Path

M_PER_DEG_LAT = 110574.0

def m_per_deg_lng(lat: float) -> float:
    return 111320.0 * math.cos(math.radians(lat))

def offset(lat, lng, dist_m, bearing_rad):
    dlat = (dist_m * math.cos(bearing_rad)) / M_PER_DEG_LAT
    dlng = (dist_m * math.sin(bearing_rad)) / m_per_deg_lng(lat)
    return lat + dlat, lng + dlng

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--district", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--out", default="artifacts/offline_val")
    ap.add_argument("--n-interior", type=int, default=400)
    ap.add_argument("--n-border", type=int, default=100)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # Truth point generation requires shapely; metrics against offline engine are phase-2.
    try:
        from shapely.geometry import shape, Point
        from shapely.validation import make_valid
    except ImportError:
        print("shapely required")
        raise

    with open(args.geojson) as f:
        feats = [ft for ft in json.load(f)["features"] if str(ft["properties"].get("district_id")) == str(args.district)]
    rng = random.Random(args.seed)
    radii = [0, 20, 100, 500, 2000, 5000, 20000]
    points = []

    # interior samples via rejection in bbox of union-ish random village
    for _ in range(args.n_interior):
        ft = feats[rng.randrange(len(feats))]
        g = shape(ft["geometry"])
        if not g.is_valid:
            g = make_valid(g)
        minx, miny, maxx, maxy = g.bounds
        for _try in range(50):
            x = rng.uniform(minx, maxx)
            y = rng.uniform(miny, maxy)
            if g.contains(Point(x, y)):
                vid = str(ft["properties"]["village_id"])
                points.append({"lat": y, "lng": x, "truth_village": vid, "kind": "interior"})
                break

    # border: points near exterior ring of random village
    for _ in range(args.n_border):
        ft = feats[rng.randrange(len(feats))]
        g = shape(ft["geometry"])
        if not g.is_valid:
            g = make_valid(g)
        # sample along boundary
        b = g.boundary
        if b.is_empty:
            continue
        t = rng.random()
        pt = b.interpolate(t, normalized=True)
        # nudge 25 m inward/outward randomly for "within 50 m"
        bearing = rng.random() * 2 * math.pi
        la, lo = offset(pt.y, pt.x, rng.uniform(5, 50), bearing)
        points.append({
            "lat": la, "lng": lo,
            "truth_village": str(ft["properties"]["village_id"]),
            "kind": "border",
        })

    # expand with noise copies for metrics table skeleton
    rows = []
    for p in points:
        for r in radii:
            bearing = rng.random() * 2 * math.pi
            la, lo = (p["lat"], p["lng"]) if r == 0 else offset(p["lat"], p["lng"], r, bearing)
            rows.append({
                "lat": la, "lng": lo, "r_m": r,
                "truth_village": p["truth_village"], "kind": p["kind"],
                # offline engine fields filled by later step
                "pred_village": None, "pred_level": None,
            })

    report = {
        "district": args.district,
        "seed": args.seed,
        "n_base_points": len(points),
        "n_rows": len(rows),
        "radii_m": radii,
        "protocol": {
            "m_per_deg_lat": M_PER_DEG_LAT,
            "m_per_deg_lng": "111320*cos(lat)",
            "noise": "exact-length offset random bearing",
        },
        "note": "pred_* filled when offline engine wired; truth from NISR village polygons",
        "sample": rows[:5],
    }
    path = out / f"district_{args.district}_seed_{args.seed}.json"
    path.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("district", "seed", "n_base_points", "n_rows")}))

if __name__ == "__main__":
    main()
