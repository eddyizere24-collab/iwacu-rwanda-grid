#!/usr/bin/env python3
"""Export hierarchy GeoJSON.gz per level from NISR village source (same as grid builders).

Source: data/rwanda_villages_full.geojson (NISR Village_Boundary via download_nisr_geometry.py).
Expected counts: 1 country / 5 provinces / 30 districts / 416 sectors / 2148 cells / 14823 villages.
CHANGED 2026-11-01 GROK: artifact-only export; do not commit geometries; see docs/HANDOFF.md
"""
from __future__ import annotations
import argparse, json, gzip, hashlib, collections
from pathlib import Path
from datetime import datetime, timezone

EXPECTED = {
    "country": 1,
    "province": 5,
    "district": 30,
    "sector": 416,
    "cell": 2148,
    "village": 14823,
}

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--out", default="artifacts/boundaries")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with open(args.geojson) as f:
        fc = json.load(f)
    feats = fc["features"]

    levels = {
        "village": [],
        "cell": {},
        "sector": {},
        "district": {},
        "province": {},
    }
    for ft in feats:
        p = ft["properties"]
        vid = str(p.get("village_id") or "").strip()
        cid = str(p.get("cell_id") or "").strip()
        sid = str(p.get("sector_id") or "").strip()
        did = str(p.get("district_id") or "").strip()
        pid = str(p.get("province_id") or "").strip()
        levels["village"].append({
            "type": "Feature",
            "properties": {
                "code": vid,
                "name": (p.get("village") or "").strip(),
                "parent_code": cid,
                "level": "village",
                "district_id": did,
            },
            "geometry": ft["geometry"],
        })
        for key, code, name_key, parent in (
            ("cell", cid, "cell", sid),
            ("sector", sid, "sector", did),
            ("district", did, "district", pid),
            ("province", pid, "province", None),
        ):
            if code and code not in levels[key]:
                levels[key][code] = {
                    "code": code,
                    "name": (p.get(name_key) or "").strip(),
                    "parent_code": parent,
                    "level": key,
                }

    counts = {
        "village": len(levels["village"]),
        "cell": len(levels["cell"]),
        "sector": len(levels["sector"]),
        "district": len(levels["district"]),
        "province": len(levels["province"]),
        "country": 1,
    }
    diffs = {k: {"expected": EXPECTED[k], "got": counts[k], "delta": counts[k] - EXPECTED[k]} for k in EXPECTED}

    manifest = {
        "source": "data/rwanda_villages_full.geojson (NISR village boundaries; download_nisr_geometry.py)",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "expected": EXPECTED,
        "differences": diffs,
        "files": [],
        "note": "Full geometries only for villages; higher levels are attribute tables (codes/names/parents) until dissolved geometries are added.",
    }

    # villages by district
    by_d = collections.defaultdict(list)
    for ft in levels["village"]:
        by_d[str(ft["properties"]["district_id"])].append(ft)

    for did, flist in sorted(by_d.items()):
        path = out / f"villages_district_{did}.geojson.gz"
        payload = json.dumps({"type": "FeatureCollection", "features": flist}, separators=(",", ":")).encode()
        with gzip.open(path, "wb", compresslevel=9) as g:
            g.write(payload)
        manifest["files"].append({
            "path": str(path.name),
            "level": "village",
            "district_id": did,
            "n": len(flist),
            "bytes_gz": path.stat().st_size,
            "sha256": sha256_file(path),
        })

    for level in ("cell", "sector", "district", "province"):
        rows = list(levels[level].values())
        path = out / f"{level}s_codes.json.gz"
        payload = json.dumps(rows, separators=(",", ":")).encode()
        with gzip.open(path, "wb", compresslevel=9) as g:
            g.write(payload)
        manifest["files"].append({
            "path": str(path.name),
            "level": level,
            "n": len(rows),
            "bytes_gz": path.stat().st_size,
            "sha256": sha256_file(path),
        })

    country = {"code": "RW", "name": "Rwanda", "level": "country", "parent_code": None}
    path = out / "country.json.gz"
    with gzip.open(path, "wb", compresslevel=9) as g:
        g.write(json.dumps(country, separators=(",", ":")).encode())
    manifest["files"].append({
        "path": path.name,
        "level": "country",
        "n": 1,
        "bytes_gz": path.stat().st_size,
        "sha256": sha256_file(path),
    })

    man_path = out / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"counts": counts, "differences": diffs, "n_files": len(manifest["files"])}, indent=2))

if __name__ == "__main__":
    main()
