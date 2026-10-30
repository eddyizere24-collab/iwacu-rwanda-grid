#!/usr/bin/env python3
"""Build adaptive geohash grid, GH4 chunks, summary pyramid, national polygon. One district at a time. For GitHub Actions."""
from __future__ import annotations
import argparse, json, gzip, hashlib, collections, math, time, urllib.request
from pathlib import Path
from datetime import datetime, timezone
try:
    from shapely.geometry import shape, mapping, Point, box
    from shapely.validation import make_valid
    import pygeohash as pgh
except ImportError as e:
    raise SystemExit(f"Need shapely+pygeohash: {e}")

VERSION = "2026.10.30.algo3"
ADM0_URL = "https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/gbOpen/RWA/ADM0/geoBoundaries-RWA-ADM0.geojson"
NISR_URL = "https://gis-server.statistics.gov.rw/server/rest/services/Hosted/Village_Boundary_2022/FeatureServer/3/query"

def encode(lat, lon, p):
    return pgh.encode(lat, lon, precision=p)

def geohash_bbox(gh):
    lat, lon, lat_err, lon_err = pgh.decode_exactly(gh)
    return (lon - lon_err, lat - lat_err, lon + lon_err, lat + lat_err)

def download_nisr(out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 1_000_000:
        print(f"Using cached {out}"); return
    feats, offset, page = [], 0, 500
    while True:
        params = f"where=1%3D1&outFields=province_id,province,district_id,district,sector_id,sector,cell_id,cell,village_id,village&returnGeometry=true&outSR=4326&f=geojson&resultOffset={offset}&resultRecordCount={page}&orderByFields=village_id+ASC"
        print(f"NISR offset {offset}...", flush=True)
        with urllib.request.urlopen(f"{NISR_URL}?{params}", timeout=90) as r:
            data = json.loads(r.read().decode())
        batch = data.get("features") or []
        if not batch: break
        feats.extend(batch)
        if len(batch) < page: break
        offset += page
        time.sleep(0.1)
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print(f"Saved {len(feats)} features")

def download_adm0(out: Path):
    if out.exists(): return
    print("Downloading geoBoundaries ADM0...", flush=True)
    with urllib.request.urlopen(ADM0_URL, timeout=90) as r:
        out.write_bytes(r.read())

def build_district_cells(feats):
    vgeoms, vmeta = {}, {}
    for feat in feats:
        p = feat["properties"]
        vid = str(p["village_id"]).strip()
        poly = shape(feat["geometry"])
        if not poly.is_valid: poly = make_valid(poly)
        c = poly.centroid
        vgeoms[vid] = poly
        vmeta[vid] = {"n": (p.get("village") or "").strip(), "c": str(p.get("cell_id") or "").strip(),
                      "s": str(p.get("sector_id") or "").strip(), "d": str(p.get("district_id") or "").strip(),
                      "p": str(p.get("province_id") or "").strip(), "lat": round(c.y, 6), "lon": round(c.x, 6)}
    step = 0.00135
    gh7_votes = collections.defaultdict(set)
    for vid, poly in vgeoms.items():
        minx, miny, maxx, maxy = poly.bounds
        x = minx
        while x <= maxx + 1e-12:
            y = miny
            while y <= maxy + 1e-12:
                if poly.covers(Point(x, y)): gh7_votes[encode(y, x, 7)].add(vid)
                y += step
            x += step
        c = poly.centroid
        gh7_votes[encode(c.y, c.x, 7)].add(vid)
    cells, primary = {}, collections.Counter()
    for h7, vids in gh7_votes.items():
        if len(vids) == 1:
            vid = next(iter(vids))
            cells[h7] = [{"v": vid, "s": 1.0}]; primary[vid] += 1
        else:
            minx, miny, maxx, maxy = geohash_bbox(h7)
            cell_box = box(minx, miny, maxx, maxy)
            areas = {}
            for vid in vids:
                try:
                    inter = vgeoms[vid].intersection(cell_box)
                    a = inter.area if not inter.is_empty else 0.0
                except Exception:
                    a = 0.0
                if a > 0: areas[vid] = a
            if not areas: areas = {vid: 1.0 for vid in vids}
            total = sum(areas.values()) or 1.0
            ranked = sorted(areas.items(), key=lambda x: -x[1])[:5]
            cells[h7] = [{"v": v, "s": round(a / total, 4)} for v, a in ranked]
            primary[ranked[0][0]] += 1
    for vid in set(vgeoms) - set(primary):
        m = vmeta[vid]
        h7 = encode(m["lat"], m["lon"], 7)
        cells[h7] = [{"v": vid, "s": 1.0}] + [t for t in cells.get(h7, []) if t["v"] != vid][:2]
    return cells, vmeta

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geojson", default="data/rwanda_villages_full.geojson")
    ap.add_argument("--out", default="artifacts/algo_out")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    geo_path = Path(args.geojson)
    download_nisr(geo_path)
    download_adm0(Path("data/geoBoundaries-RWA-ADM0.geojson"))
    print("Loading geojson...", flush=True)
    with open(geo_path) as f:
        fc = json.load(f)
    by_dist = collections.defaultdict(list)
    for feat in fc["features"]:
        by_dist[str(feat["properties"]["district_id"])].append(feat)
    del fc
    all_cells, all_vmeta = {}, {}
    for did in sorted(by_dist.keys()):
        print(f"District {did} ({len(by_dist[did])} v)...", flush=True)
        cells, vmeta = build_district_cells(by_dist[did])
        all_cells.update(cells); all_vmeta.update(vmeta)
        del by_dist[did]
        print(f"  cells so far {len(all_cells)}", flush=True)
    by_gh4 = collections.defaultdict(list)
    for g, shares in all_cells.items():
        by_gh4[g[:4]].append({"g": g, "t": shares})
    chunk_dir = out / "chunks_gh4"; chunk_dir.mkdir(exist_ok=True)
    manifest_files = []
    for prefix, cells in sorted(by_gh4.items()):
        vids = set(t["v"] for c in cells for t in c["t"])
        vlookup = {vid: all_vmeta[vid] for vid in vids if vid in all_vmeta}
        raw = json.dumps({"v": VERSION, "prefix": prefix, "cells": cells, "villages": vlookup}, separators=(",", ":")).encode()
        (chunk_dir / f"{prefix}.json").write_bytes(raw)
        gz = chunk_dir / f"{prefix}.json.gz"
        with gzip.open(gz, "wb", compresslevel=9) as f: f.write(raw)
        manifest_files.append({"file": f"chunks_gh4/{prefix}.json.gz", "bytes_gz": gz.stat().st_size,
                               "sha256": hashlib.sha256(gz.read_bytes()).hexdigest(), "cells": len(cells)})
    print(f"GH4 prefixes {len(manifest_files)}", flush=True)
    buckets = collections.defaultdict(lambda: collections.Counter())
    for g, shares in all_cells.items():
        for t in shares: buckets[g[:5]][t["v"]] += t["s"]
    g5 = {}
    for key, ctr in buckets.items():
        total = sum(ctr.values()) or 1
        ranked = sorted(ctr.items(), key=lambda x: -x[1])[:3]
        top_v = [[v, round(c / total, 3)] for v, c in ranked]
        cell_c, sec_c, dist_c, prov_c = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
        for v, s in ctr.items():
            m = all_vmeta.get(v)
            if not m: continue
            w = s / total
            cell_c[m["c"]] += w; sec_c[m["s"]] += w; dist_c[m["d"]] += w; prov_c[m["p"]] += w
        def topn(c, n=2):
            return [[i, round(s, 3)] for i, s in sorted(c.items(), key=lambda x: -x[1])[:n]]
        g5[key] = [top_v, topn(cell_c), topn(sec_c), topn(dist_c), topn(prov_c)]
    adm0 = json.loads(Path("data/geoBoundaries-RWA-ADM0.geojson").read_text())
    national = shape(adm0["features"][0]["geometry"])
    if not national.is_valid: national = make_valid(national)
    national = make_valid(national.buffer(0.01))
    nat_fc = {"type": "FeatureCollection", "source_adm0": ADM0_URL,
              "source_kivu_border": "geoBoundaries RWA ADM0 international boundary through Lake Kivu",
              "features": [{"type": "Feature", "properties": {"name": "Rwanda"}, "geometry": mapping(national)}]}
    nat_path = Path("data/rwanda_national.geojson"); nat_path.parent.mkdir(exist_ok=True)
    nat_bytes = json.dumps(nat_fc, separators=(",", ":")).encode(); nat_path.write_bytes(nat_bytes)
    pyramid = {"v": VERSION, "g5": g5, "bbox": {"lat_min": national.bounds[1], "lat_max": national.bounds[3],
              "lon_min": national.bounds[0], "lon_max": national.bounds[2]}}
    pyr_raw = json.dumps(pyramid, separators=(",", ":")).encode()
    with gzip.open(out / "summary_pyramid.json.gz", "wb", compresslevel=9) as f: f.write(pyr_raw)
    (out / "summary_pyramid.json").write_bytes(pyr_raw)
    never = sorted(set(all_vmeta) - {shares[0]["v"] for shares in all_cells.values() if shares})
    man = {"dataset_version": VERSION, "built_at": datetime.now(timezone.utc).isoformat(),
           "village_total": len(all_vmeta), "never_primary": len(never), "gh7_cells": len(all_cells),
           "gh4_files": manifest_files, "summary_pyramid_gz_bytes": (out / "summary_pyramid.json.gz").stat().st_size,
           "national_geojson_sha256": hashlib.sha256(nat_bytes).hexdigest(),
           "max_chunk_gz": max(f["bytes_gz"] for f in manifest_files),
           "p95_chunk_gz": sorted(f["bytes_gz"] for f in manifest_files)[int(0.95 * len(manifest_files))]}
    json.dump(man, open(out / "manifest.json", "w"), indent=2)
    json.dump(man, open("data/manifest.json", "w"), indent=2)
    print("DONE", man["village_total"], man["never_primary"], man["max_chunk_gz"])

if __name__ == "__main__":
    main()
