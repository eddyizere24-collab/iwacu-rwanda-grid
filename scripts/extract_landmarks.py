#!/usr/bin/env python3
"""Extract named POIs from Geofabrik rwanda-latest.osm.pbf into geohash5 tiles.

ODbL only — never merge NISR. CHANGED 2026-11-01 GROK: see docs/HANDOFF.md
"""
from __future__ import annotations
import argparse, gzip, json, hashlib
from pathlib import Path

# Tags → type
TAG_MAP = {
    ("amenity", "school"): "school",
    ("amenity", "university"): "school",
    ("amenity", "college"): "school",
    ("amenity", "kindergarten"): "school",
    ("amenity", "hospital"): "health",
    ("amenity", "clinic"): "health",
    ("amenity", "doctors"): "health",
    ("amenity", "pharmacy"): "health",
    ("amenity", "marketplace"): "market",
    ("amenity", "place_of_worship"): "worship",
    ("amenity", "drinking_water"): "water",
    ("amenity", "water_point"): "water",
    ("amenity", "bus_station"): "bus",
    ("highway", "bus_stop"): "bus",
    ("amenity", "police"): "police",
    ("amenity", "bank"): "bank",
    ("amenity", "fuel"): "fuel",
    ("office", "government"): "admin",
    ("amenity", "townhall"): "admin",
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pbf", default="data/rwanda-latest.osm.pbf")
    ap.add_argument("--out", default="artifacts/landmarks")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # Prefer pyosmium if available
    try:
        import osmium
        import pygeohash as pgh
    except ImportError:
        print("pip install osmium pygeohash")
        raise

    class Handler(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.items = []
        def node(self, n):
            if not n.location.valid():
                return
            tags = {t.k: t.v for t in n.tags}
            name = tags.get("name") or tags.get("name:rw") or tags.get("name:en")
            if not name:
                return
            typ = None
            for (k, v), t in TAG_MAP.items():
                if tags.get(k) == v:
                    typ = t
                    break
            if not typ:
                return
            lat, lng = n.location.lat, n.location.lon
            self.items.append({
                "id": f"n{n.id}",
                "osm_id": n.id,
                "name": name,
                "type": typ,
                "lat": lat,
                "lng": lng,
                "gh5": pgh.encode(lat, lng, 5),
            })

    h = Handler()
    h.apply_file(args.pbf, locations=True)
    tiles = {}
    for it in h.items:
        tiles.setdefault(it["gh5"], []).append(it)
    for gh5, rows in tiles.items():
        path = out / f"{gh5}.json.gz"
        payload = json.dumps(rows, separators=(",", ":")).encode()
        with gzip.open(path, "wb", compresslevel=9) as f:
            f.write(payload)
    manifest = {
        "count": len(h.items),
        "tiles": len(tiles),
        "max_tile": max((len(v) for v in tiles.values()), default=0),
        "types": sorted({it["type"] for it in h.items}),
        "attribution": "© OpenStreetMap contributors, ODbL",
        "source": "Geofabrik rwanda-latest.osm.pbf",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
