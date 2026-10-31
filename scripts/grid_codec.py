#!/usr/bin/env python3
"""Binary IRG1 codec + longest-prefix lookup for shipped root.bin.gz / gh6/*.bin.gz."""
from __future__ import annotations
import gzip, struct
from pathlib import Path

BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"

def uvarint_read(buf: bytes, i: int):
    shift = 0
    n = 0
    while True:
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        if b < 0x80:
            return n, i
        shift += 7

def int_to_gh(n: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(BASE32[n % 32])
        n //= 32
    return "".join(reversed(chars))

def read_binary_chunk(data: bytes, vid_order: list[str] | None = None):
    """Return dict gh -> {pure, shares:[(vid,s)], prec}."""
    if data[:4] != b"IRG1":
        raise ValueError("bad magic")
    i = 4
    count, i = uvarint_read(data, i)
    prev = 0
    cells = {}
    for _ in range(count):
        delta, i = uvarint_read(data, i)
        cur = prev + delta
        prev = cur
        key_len = data[i]
        i += 1
        gh = int_to_gh(cur, key_len)
        flag = data[i]
        i += 1
        if flag == 1:
            vi, i = uvarint_read(data, i)
            vid = vid_order[vi] if vid_order else str(vi)
            cells[gh] = {"pure": True, "shares": [(vid, 1.0)], "prec": key_len}
        else:
            nshares = data[i]
            i += 1
            shares = []
            for _s in range(nshares):
                vi, i = uvarint_read(data, i)
                q = struct.unpack_from(">H", data, i)[0]
                i += 2
                vid = vid_order[vi] if vid_order else str(vi)
                shares.append((vid, q / 65535.0))
            cells[gh] = {"pure": False, "shares": shares, "prec": key_len}
    return cells

def load_root(path: Path):
    raw = gzip.open(path, "rb").read()
    jlen = struct.unpack_from(">I", raw, 0)[0]
    meta = __import__("json").loads(raw[4 : 4 + jlen].decode())
    vid_order = meta.get("vid_order") or list(meta.get("villages", {}).keys())
    cells = read_binary_chunk(raw[4 + jlen :], vid_order)
    return meta, cells, vid_order

def load_gh6_file(path: Path, vid_order: list[str]):
    return read_binary_chunk(gzip.open(path, "rb").read(), vid_order)

def longest_prefix(gh: str, index: dict):
    """Resolve point's geohash by longest stored ancestor (exact key or shorter prefix)."""
    for L in range(len(gh), 3, -1):
        key = gh[:L]
        if key in index:
            return key, index[key]
    return None, None

class ShippedIndex:
    def __init__(self, out_dir: Path):
        self.out = Path(out_dir)
        self.meta, self.root_cells, self.vid_order = load_root(self.out / "root.bin.gz")
        self.gh6_cache = {}
        self.all = dict(self.root_cells)

    def _ensure_gh6(self, prefix6: str):
        if prefix6 in self.gh6_cache:
            return
        p = self.out / "gh6" / f"{prefix6}.bin.gz"
        if p.exists():
            cells = load_gh6_file(p, self.vid_order)
            self.gh6_cache[prefix6] = cells
            self.all.update(cells)
        else:
            self.gh6_cache[prefix6] = {}

    def resolve(self, lat: float, lon: float):
        import pygeohash as pgh
        gh9 = pgh.encode(lat, lon, 9)
        # load possible gh6 files for prefixes of this point
        self._ensure_gh6(gh9[:6])
        # also try parent gh6 neighbors rarely needed for border; skip for speed
        key, info = longest_prefix(gh9, self.all)
        return key, info, gh9
