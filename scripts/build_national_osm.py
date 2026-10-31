#!/usr/bin/env python3
"""National = village_union UNION OSM Nominatim Rwanda boundary (includes Kivu share)."""
from __future__ import annotations
import argparse, json, hashlib, math, urllib.request, urllib.parse, collections
from pathlib import Path
from shapely.geometry import shape, mapping, Point, box
from shapely.ops import unary_union
from shapely.validation import make_valid
from shapely.prepared import prep

OFFICIAL_KM2 = 26338  # CIA World Factbook / common published total area km2
NOMINATIM = "https://nominatim.openstreetmap.org/search"
ADM0_URL = "https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/gbOpen/RWA/ADM0/geoBoundaries-RWA-ADM0.geojson"
LAT_M = 110574.0

def deg2_km2(a, lat=-2.0):
    return a * LAT_M * (111320.0 * math.cos(math.radians(lat))) / 1e6

def download_osm_rwanda(path: Path):
    q = urllib.parse.urlencode({"country": "Rwanda", "format": "json", "polygon_geojson": 1, "limit": 1})
    req = urllib.request.Request(f"{NOMINATIM}?{q}", headers={"User-Agent": "iwacu-rwanda-grid/1.0 (research)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
    if not data or not data[0].get("geojson"):
        raise SystemExit("Nominatim empty")
    geom = data[0]["geojson"]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"source": "OSM/Nominatim", "display_name": data[0].get("display_name")}, "geometry": geom}]}))
    return shape(geom)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--out", default="data/rwanda_national.geojson")
    ap.add_argument("--meta", default="data/rwanda_national_meta.json")
    args = ap.parse_args()
    print("Downloading OSM Rwanda via Nominatim...", flush=True)
    osm = download_osm_rwanda(Path("data/osm_rwanda_boundary.geojson"))
    if not osm.is_valid:
        osm = make_valid(osm)
    print(f"OSM area_km2={deg2_km2(osm.area):.1f}", flush=True)
    adm0_path = Path("data/geoBoundaries-RWA-ADM0.geojson")
    if not adm0_path.exists():
        with urllib.request.urlopen(ADM0_URL, timeout=90) as r:
            adm0_path.write_bytes(r.read())
    gb = shape(json.loads(adm0_path.read_text())["features"][0]["geometry"])
    if not gb.is_valid:
        gb = make_valid(gb)
    with open(args.geojson) as f:
        feats = json.load(f)["features"]
    by_d = collections.defaultdict(list)
    for feat in feats:
        by_d[str(feat["properties"]["district_id"])].append(feat)
    unions = []
    for did in sorted(by_d.keys()):
        polys = []
        for feat in by_d[did]:
            g = shape(feat["geometry"])
            if not g.is_valid:
                g = make_valid(g)
            polys.append(g)
        unions.append(unary_union(polys))
        print(f"  dist {did}", flush=True)
    village_union = unary_union(unions)
    if not village_union.is_valid:
        village_union = make_valid(village_union)
    national = unary_union([village_union, osm])
    if not national.is_valid:
        national = make_valid(national)
    national = make_valid(national.buffer(0.00009).buffer(-0.00009))
    added = national.difference(village_union)
    kivu_box = box(28.75, -2.60, 29.45, -1.55)
    kivu_a = added.intersection(kivu_box).area if not added.is_empty else 0
    else_a = max(0.0, (added.area if not added.is_empty else 0) - kivu_a)
    pieces = []
    if not added.is_empty:
        geoms = list(added.geoms) if added.geom_type == "MultiPolygon" else [added]
        for g in geoms:
            pieces.append((deg2_km2(g.area), g.centroid.y, g.centroid.x))
        pieces.sort(reverse=True)
    prep_n = prep(national)
    uncovered = sum(1 for feat in feats if not prep_n.contains(Point(shape(feat["geometry"]).centroid.x, shape(feat["geometry"]).centroid.y)))
    simplified = national.simplify(0.00023, preserve_topology=True)
    fc = {"type": "FeatureCollection", "source": "union(NISR villages, OSM Nominatim Rwanda)",
          "official_area_km2_ref": OFFICIAL_KM2,
          "features": [{"type": "Feature", "properties": {"name": "Rwanda", "area_km2": round(deg2_km2(national.area), 1)},
                        "geometry": mapping(simplified)}]}
    raw = json.dumps(fc, separators=(",", ":")).encode()
    Path(args.out).write_bytes(raw)
    meta = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "national_area_km2": round(deg2_km2(national.area), 1),
            "village_union_area_km2": round(deg2_km2(village_union.area), 1),
            "osm_area_km2": round(deg2_km2(osm.area), 1),
            "geoboundaries_area_km2": round(deg2_km2(gb.area), 1),
            "official_km2": OFFICIAL_KM2,
            "pct_of_official": round(100 * deg2_km2(national.area) / OFFICIAL_KM2, 2),
            "added_kivu_km2": round(deg2_km2(kivu_a), 1),
            "added_elsewhere_km2": round(deg2_km2(else_a), 1),
            "uncovered_villages": uncovered,
            "largest_outside_pieces": [{"km2": round(a, 2), "lat": round(la, 5), "lng": round(lo, 5)} for a, la, lo in pieces[:5]],
            "boundary_source": "OSM via Nominatim polygon_geojson country=Rwanda",
            "official_source": "CIA World Factbook common figure ~26338 km2 total"}
    Path(args.meta).write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    print("DONE national OSM")

if __name__ == "__main__":
    main()
