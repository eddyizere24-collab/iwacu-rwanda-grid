#!/usr/bin/env python3
"""IRG2 binary codec: length-prefixed geohash strings (no int delta across mixed lengths).

IRG1 int-delta was broken for mixed key lengths -> 94% missing. Client uses longest-prefix.
"""
from __future__ import annotations
import gzip, struct, json
from pathlib import Path

BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
MAGIC = b"IRG2"

def uvarint_write(n: int) -> bytes:
    out = bytearray()
    while n > 0x7F:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n & 0x7F)
    return bytes(out)

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

def write_binary_chunk(cells: dict, village_index: dict[str, int]) -> bytes:
    items = sorted(cells.items(), key=lambda x: x[0])
    buf = bytearray()
    buf += MAGIC
    buf += uvarint_write(len(items))
    for gh, info in items:
        gb = gh.encode("ascii")
        buf += bytes([len(gb)])
        buf += gb
        if info["pure"]:
            buf += b"\x01"
            buf += uvarint_write(village_index[info["shares"][0][0]])
        else:
            buf += b"\x00"
            shares = info["shares"][:5]
            buf += bytes([len(shares)])
            for vid, s in shares:
                buf += uvarint_write(village_index[vid])
                q = max(0, min(65535, int(round(s * 65535))))
                buf += struct.pack(">H", q)
    return bytes(buf)

def read_binary_chunk(data: bytes, vid_order: list[str] | None = None):
    if data[:4] not in (b"IRG2", b"IRG1"):
        raise ValueError(f"bad magic {data[:4]!r}")
    magic = data[:4]
    i = 4
    count, i = uvarint_read(data, i)
    cells = {}
    if magic == b"IRG2":
        for _ in range(count):
            klen = data[i]
            i += 1
            gh = data[i : i + klen].decode("ascii")
            i += klen
            flag = data[i]
            i += 1
            if flag == 1:
                vi, i = uvarint_read(data, i)
                vid = vid_order[vi] if vid_order else str(vi)
                cells[gh] = {"pure": True, "shares": [(vid, 1.0)], "prec": len(gh)}
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
                cells[gh] = {"pure": False, "shares": shares, "prec": len(gh)}
    else:
        # legacy IRG1 (broken for mixed lengths; kept for diagnostics)
        prev = 0
        for _ in range(count):
            delta, i = uvarint_read(data, i)
            cur = prev + delta
            prev = cur
            key_len = data[i]
            i += 1
            n = cur
            chars = []
            for _k in range(key_len):
                chars.append(BASE32[n % 32])
                n //= 32
            gh = "".join(reversed(chars))
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
    meta = json.loads(raw[4 : 4 + jlen].decode())
    vid_order = meta.get("vid_order") or list(meta.get("villages", {}).keys())
    cells = read_binary_chunk(raw[4 + jlen :], vid_order)
    return meta, cells, vid_order

def load_gh6_file(path: Path, vid_order: list[str]):
    return read_binary_chunk(gzip.open(path, "rb").read(), vid_order)

def longest_prefix(gh: str, index: dict):
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
        self._ensure_gh6(gh9[:6])
        key, info = longest_prefix(gh9, self.all)
        return key, info, gh9
