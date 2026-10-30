#!/usr/bin/env python3
"""Download NISR Village_Boundary_2022 full geometry. Deterministic, public data only."""
import json, urllib.request, time, hashlib, sys
from pathlib import Path

BASE = "https://gis-server.statistics.gov.rw/server/rest/services/Hosted/Village_Boundary_2022/FeatureServer/3/query"
OUT = Path(__file__).resolve().parents[1] / "data" / "rwanda_villages_full.geojson"
PAGE = 500

def main():
    feats = []
    offset = 0
    while True:
        params = (
            f"where=1%3D1&outFields=province_id,province,district_id,district,"
            f"sector_id,sector,cell_id,cell,village_id,village"
            f"&returnGeometry=true&outSR=4326&f=geojson"
            f"&resultOffset={offset}&resultRecordCount={PAGE}&orderByFields=village_id+ASC"
        )
        url = f"{BASE}?{params}"
        print(f"offset {offset}...", flush=True)
        req = urllib.request.Request(url, headers={"Accept": "application/geo+json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read().decode())
        batch = data.get("features") or []
        if not batch:
            break
        feats.extend(batch)
        print(f"  {len(batch)} total {len(feats)}")
        if len(batch) < PAGE:
            break
        offset += PAGE
        time.sleep(0.1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f)
    print(f"Saved {len(feats)} features to {OUT}")
    # quick null check
    nulls = sum(1 for f in feats if not (f.get("geometry") or {}).get("coordinates"))
    print(f"null/empty geometry: {nulls}")

if __name__ == "__main__":
    main()
