#!/usr/bin/env python3
"""Extract the ~1009 km2 Kivu water piece outside villages; simplify national + piece at 100m."""
from __future__ import annotations
import argparse, json, hashlib, math
from pathlib import Path
from shapely.geometry import shape, mapping, box
from shapely.ops import unary_union
from shapely.validation import make_valid

LAT_M = 110574.0
SIMPLIFY_DEG = 100.0 / LAT_M  # ~100 m

def deg2_km2(a, lat=-2.0):
    return a * LAT_M * (111320.0 * math.cos(math.radians(lat))) / 1e6

def n_vertices(g):
    if g.geom_type == "Polygon":
        return len(g.exterior.coords) + sum(len(r.coords) for r in g.interiors)
    if g.geom_type == "MultiPolygon":
        return sum(n_vertices(p) for p in g.geoms)
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--national", default="data/rwanda_national.geojson")
    ap.add_argument("--villages", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--out-piece", default="data/kivu_water_piece.geojson")
    ap.add_argument("--out-national", default="data/rwanda_national.geojson")
    ap.add_argument("--meta", default="data/kivu_piece_meta.json")
    args = ap.parse_args()

    nat = shape(json.loads(Path(args.national).read_text())["features"][0]["geometry"])
    if not nat.is_valid:
        nat = make_valid(nat)

    with open(args.villages) as f:
        feats = json.load(f)["features"]
    # district-by-district union to save memory
    from collections import defaultdict
    by_d = defaultdict(list)
    for feat in feats:
        by_d[str(feat["properties"]["district_id"])].append(shape(feat["geometry"]))
    unions = []
    for did in sorted(by_d):
        polys = [make_valid(g) if not g.is_valid else g for g in by_d[did]]
        unions.append(unary_union(polys))
        print("union", did, flush=True)
    villages = unary_union(unions)
    if not villages.is_valid:
        villages = make_valid(villages)

    added = nat.difference(villages)
    kivu_box = box(28.75, -2.60, 29.45, -1.55)
    kivu = added.intersection(kivu_box) if not added.is_empty else added
    area_before = deg2_km2(kivu.area)
    verts_before = n_vertices(kivu)
    kivu_s = kivu.simplify(SIMPLIFY_DEG, preserve_topology=True)
    area_after = deg2_km2(kivu_s.area)
    verts_after = n_vertices(kivu_s)
    piece_fc = {
        "type": "FeatureCollection",
        "name": "kivu_water_piece",
        "note": "Rwanda share of Lake Kivu outside NISR village polygons",
        "features": [{
            "type": "Feature",
            "properties": {
                "name": "Kivu water (Rwanda)",
                "area_km2_before": round(area_before, 2),
                "area_km2_after": round(area_after, 2),
                "centroid_lat": round(kivu_s.centroid.y, 5),
                "centroid_lng": round(kivu_s.centroid.x, 5),
            },
            "geometry": mapping(kivu_s),
        }],
    }
    piece_raw = json.dumps(piece_fc, separators=(",", ":")).encode()
    Path(args.out_piece).write_bytes(piece_raw)

    nat_s = nat.simplify(SIMPLIFY_DEG, preserve_topology=True)
    nat_fc = {
        "type": "FeatureCollection",
        "source": "union(NISR villages, OSM Nominatim Rwanda)",
        "simplify_m": 100,
        "features": [{
            "type": "Feature",
            "properties": {"name": "Rwanda", "area_km2": round(deg2_km2(nat_s.area), 1)},
            "geometry": mapping(nat_s),
        }],
    }
    nat_raw = json.dumps(nat_fc, separators=(",", ":")).encode()
    Path(args.out_national).write_bytes(nat_raw)

    meta = {
        "kivu_sha256": hashlib.sha256(piece_raw).hexdigest(),
        "kivu_bytes": len(piece_raw),
        "kivu_kb": round(len(piece_raw) / 1024, 2),
        "kivu_vertices_before": verts_before,
        "kivu_vertices_after": verts_after,
        "kivu_area_km2_before": round(area_before, 2),
        "kivu_area_km2_after": round(area_after, 2),
        "kivu_centroid": {"lat": round(kivu_s.centroid.y, 5), "lng": round(kivu_s.centroid.x, 5)},
        "national_sha256": hashlib.sha256(nat_raw).hexdigest(),
        "national_bytes": len(nat_raw),
        "national_kb": round(len(nat_raw) / 1024, 2),
        "national_area_km2": round(deg2_km2(nat_s.area), 1),
        "simplify_m": 100,
    }
    Path(args.meta).write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))

if __name__ == "__main__":
    main()
