#!/usr/bin/env python3
"""Shared validation helpers for IWACU grid (PIP, Gaussian locate)."""
from __future__ import annotations
import math, collections
from pathlib import Path
import json
try:
    from shapely.geometry import shape, Point
    from shapely.validation import make_valid
    from shapely.prepared import prep
    import pygeohash as pgh
except ImportError as e:
    raise SystemExit(f"Need shapely+pygeohash: {e}")

SEED_TUNE, SEED_TEST = 424242, 20261030
NOISES = [0, 20, 100, 500, 2000, 5000, 20000]
LAT_M = 110574.0

def lng_m(lat):
    return 111320.0 * max(0.3, abs(math.cos(math.radians(lat))))

def encode(lat, lon, p):
    return pgh.encode(lat, lon, precision=p)

def center(gh):
    la, lo, _, _ = pgh.decode_exactly(gh)
    return la, lo

def haversine_m(a, b, c, d):
    R, p = 6371000, math.pi / 180
    x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1, x)))

def load_cells(chunk_dir, district_id):
    cell_map, meta = {}, {}
    for p in sorted(Path(chunk_dir).glob("*.json")):
        ch = json.loads(p.read_text())
        for vid, m in ch.get("villages", {}).items():
            if m.get("d") == district_id:
                meta[vid] = m
        for c in ch.get("cells", []):
            keep = any(
                t["v"] in meta
                or (t["v"] in ch.get("villages", {}) and ch["villages"][t["v"]].get("d") == district_id)
                for t in c["t"]
            )
            if keep:
                cell_map[c["g"]] = c["t"]
                for t in c["t"]:
                    if t["v"] in ch.get("villages", {}):
                        meta[t["v"]] = ch["villages"][t["v"]]
    return cell_map, meta

def locate_gauss(lat, lng, a, cell_map, meta, national_prep, tau=0.80):
    flags = []
    if national_prep is not None and not national_prep.contains(Point(lng, lat)):
        return {"finestLevel": "unknown", "flags": ["outside_rwanda"], "top": [], "chosen_id": None, "Pv_top1": 0}
    sigma = 1e-6 if a <= 10 else a / 1.51
    votes, wsum = collections.Counter(), 0.0
    step = 150 / LAT_M
    n = max(1, int(math.ceil(3 * max(sigma, 50) / 150)))
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            la = lat + i * step
            lo = lng + j * step * (LAT_M / lng_m(lat))
            gh = encode(la, lo, 7)
            shares = cell_map.get(gh)
            if not shares:
                continue
            clat, clon = center(gh)
            d = haversine_m(lat, lng, clat, clon)
            if d > 3 * max(sigma, 1) + 80:
                continue
            w = 1.0 if sigma < 1e-5 else math.exp(-d * d / (2 * sigma * sigma))
            wsum += w
            for t in shares:
                votes[t["v"]] += w * t["s"]
    if wsum <= 0:
        best, bestd = None, 1e18
        for vid, m in meta.items():
            d = haversine_m(lat, lng, m["lat"], m["lon"])
            if d < bestd:
                bestd, best = d, vid
        if best:
            votes[best] = 1.0
            wsum = 1.0
            flags.append("nearest_fallback")
    Pv = {v: s / wsum for v, s in votes.items()} if wsum else {}
    ranked = sorted(Pv.items(), key=lambda x: -x[1])
    Pc = collections.Counter()
    Ps = collections.Counter()
    Pd = collections.Counter()
    Pp = collections.Counter()
    for v, pr in Pv.items():
        m = meta.get(v)
        if not m:
            continue
        Pc[m["c"]] += pr
        Ps[m["s"]] += pr
        Pd[m["d"]] += pr
        Pp[m["p"]] += pr

    def top1(c):
        if not c:
            return 0.0, None
        k, val = max(c.items(), key=lambda x: x[1])
        return val, k

    levels = [
        ("village", ranked[0][1] if ranked else 0, ranked[0][0] if ranked else None),
        ("cell",) + top1(Pc),
        ("sector",) + top1(Ps),
        ("district",) + top1(Pd),
        ("province",) + top1(Pp),
    ]
    chosen = levels[-1]
    for L in levels:
        if L[1] >= tau:
            chosen = L
            break
    return {
        "finestLevel": chosen[0],
        "chosen_id": chosen[2],
        "top": ranked[:3],
        "flags": flags,
        "Pv_top1": ranked[0][1] if ranked else 0,
    }

def random_interior(poly, rng, n_try=40):
    minx, miny, maxx, maxy = poly.bounds
    for _ in range(n_try):
        x = rng.uniform(minx, maxx)
        y = rng.uniform(miny, maxy)
        if poly.covers(Point(x, y)):
            return y, x
    c = poly.centroid
    return c.y, c.x

def load_national_prep(path):
    if not Path(path).exists():
        return None
    nat = json.loads(Path(path).read_text())
    g = shape(nat["features"][0]["geometry"])
    if not g.is_valid:
        g = make_valid(g)
    return prep(g)
