#!/usr/bin/env python3
"""Build data/rwanda_national.geojson = unary_union(villages) UNION ADM0. District-by-district. Sliver <=10m. No 0.01deg buffer."""
from __future__ import annotations
import argparse, json, hashlib, math, urllib.request, collections
from pathlib import Path
from shapely.geometry import shape, mapping, Point, box
from shapely.ops import unary_union
from shapely.validation import make_valid
from shapely.prepared import prep

ADM0_URL = "https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/gbOpen/RWA/ADM0/geoBoundaries-RWA-ADM0.geojson"
KIVU_BBOX = (28.75, -2.60, 29.45, -1.55)
SLIVER_DEG = 0.00009
LAT_M = 110574.0

def deg2_to_km2(area_deg2, lat=-2.0):
    return area_deg2 * LAT_M * (111320.0 * math.cos(math.radians(lat))) / 1e6

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--adm0", default="data/geoBoundaries-RWA-ADM0.geojson")
    ap.add_argument("--out", default="data/rwanda_national.geojson")
    ap.add_argument("--meta", default="data/rwanda_national_meta.json")
    args = ap.parse_args()
    adm0_path = Path(args.adm0)
    if not adm0_path.exists():
        print("Downloading ADM0...", flush=True)
        with urllib.request.urlopen(ADM0_URL, timeout=90) as r:
            adm0_path.write_bytes(r.read())
    adm0 = json.loads(adm0_path.read_text())
    national_adm0 = shape(adm0["features"][0]["geometry"])
    if not national_adm0.is_valid:
        national_adm0 = make_valid(national_adm0)
    print(f"ADM0 area_km2={deg2_to_km2(national_adm0.area):.1f}", flush=True)
    with open(args.geojson) as f:
        feats = json.load(f)["features"]
    by_dist = collections.defaultdict(list)
    for feat in feats:
        by_dist[str(feat["properties"]["district_id"])].append(feat)
    print(f"villages={len(feats)} districts={len(by_dist)}", flush=True)
    district_unions, all_centroids = [], []
    for did in sorted(by_dist.keys()):
        polys = []
        for feat in by_dist[did]:
            g = shape(feat["geometry"])
            if not g.is_valid:
                g = make_valid(g)
            polys.append(g)
            c = g.centroid
            all_centroids.append((str(feat["properties"]["village_id"]), c.x, c.y, g))
        u = unary_union(polys)
        if not u.is_valid:
            u = make_valid(u)
        district_unions.append(u)
        print(f"  district {did}: {len(polys)} polys", flush=True)
        del by_dist[did]
    print("Merging district unions...", flush=True)
    village_union = unary_union(district_unions)
    if not village_union.is_valid:
        village_union = make_valid(village_union)
    print(f"village_union area_km2={deg2_to_km2(village_union.area):.1f}", flush=True)
    national = unary_union([village_union, national_adm0])
    if not national.is_valid:
        national = make_valid(national)
    national = make_valid(national.buffer(SLIVER_DEG).buffer(-SLIVER_DEG))
    print(f"national area_km2={deg2_to_km2(national.area):.1f}", flush=True)
    prep_n = prep(national)
    uncovered = []
    for vid, x, y, g in all_centroids:
        if not prep_n.contains(Point(x, y)) and not national.intersects(g):
            uncovered.append(vid)
    print(f"uncovered_villages={len(uncovered)} {uncovered[:10]}", flush=True)
    try:
        added = national.difference(village_union)
        added_area = added.area if not added.is_empty else 0.0
        kivu_box = box(*KIVU_BBOX)
        kivu_added = added.intersection(kivu_box).area if not added.is_empty else 0.0
        elsewhere_added = max(0.0, added_area - kivu_added)
    except Exception as e:
        print("area split error", e)
        kivu_added = elsewhere_added = -1
    simplified = national.simplify(0.00023, preserve_topology=True)
    nat_fc = {
        "type": "FeatureCollection",
        "name": "rwanda_national",
        "source_adm0": ADM0_URL,
        "source_villages": "NISR Village_Boundary_2022",
        "source_kivu_border": "geoBoundaries RWA ADM0 international boundary through Lake Kivu",
        "sliver_tolerance_deg": SLIVER_DEG,
        "features": [{"type": "Feature", "properties": {"name": "Rwanda", "area_km2_approx": round(deg2_to_km2(national.area), 1)}, "geometry": mapping(simplified)}],
    }
    raw = json.dumps(nat_fc, separators=(",", ":")).encode()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    meta = {
        "sha256": sha, "bytes": len(raw), "village_total": len(all_centroids),
        "uncovered_villages": len(uncovered), "uncovered_ids": uncovered[:50],
        "village_union_area_km2": round(deg2_to_km2(village_union.area), 1),
        "national_area_km2": round(deg2_to_km2(national.area), 1),
        "added_kivu_km2": round(deg2_to_km2(kivu_added), 1) if kivu_added >= 0 else None,
        "added_elsewhere_km2": round(deg2_to_km2(elsewhere_added), 1) if elsewhere_added >= 0 else None,
        "elsewhere_note": "ADM0 land beyond NISR village polygons (border strips, parks, unclassified)",
        "sliver_tolerance_m": 10, "source_adm0": ADM0_URL,
    }
    Path(args.meta).write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    if uncovered:
        raise SystemExit(f"FAIL: {len(uncovered)} villages not covered")
    print("DONE national polygon")

if __name__ == "__main__":
    main()
