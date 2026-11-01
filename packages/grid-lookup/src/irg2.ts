/**
 * IRG2 binary decoder (length-prefixed ASCII geohash keys).
 * CHANGED 2026-11-01 GROK: pure TS port of scripts/grid_codec.py IRG2; see docs/HANDOFF.md
 */
export type Share = { v: string; s: number };
export type CellInfo = { pure: boolean; shares: Share[]; prec: number };

function readUvarint(buf: Uint8Array, i: number): [number, number] {
  let shift = 0, n = 0;
  while (true) {
    const b = buf[i++];
    n |= (b & 0x7f) << shift;
    if (b < 0x80) return [n >>> 0, i];
    shift += 7;
  }
}

const te = new TextDecoder("ascii");

export function readIrg2(data: Uint8Array, vidOrder: string[]): Map<string, CellInfo> {
  if (data.length < 4 || data[0] !== 0x49 || data[1] !== 0x52 || data[2] !== 0x47 || data[3] !== 0x32)
    throw new Error("bad IRG2 magic");
  let i = 4, count = 0;
  [count, i] = readUvarint(data, i);
  const cells = new Map<string, CellInfo>();
  for (let c = 0; c < count; c++) {
    const klen = data[i++];
    const gh = te.decode(data.subarray(i, i + klen));
    i += klen;
    const flag = data[i++];
    if (flag === 1) {
      let vi = 0;
      [vi, i] = readUvarint(data, i);
      cells.set(gh, { pure: true, shares: [{ v: vidOrder[vi] ?? String(vi), s: 1 }], prec: klen });
    } else {
      const nshares = data[i++];
      const shares: Share[] = [];
      for (let s = 0; s < nshares; s++) {
        let vi = 0;
        [vi, i] = readUvarint(data, i);
        const q = (data[i] << 8) | data[i + 1];
        i += 2;
        shares.push({ v: vidOrder[vi] ?? String(vi), s: q / 65535 });
      }
      cells.set(gh, { pure: false, shares, prec: klen });
    }
  }
  return cells;
}

export function longestPrefix(gh: string, index: Map<string, CellInfo>): { key: string; info: CellInfo } | null {
  for (let L = gh.length; L > 3; L--) {
    const key = gh.slice(0, L);
    const info = index.get(key);
    if (info) return { key, info };
  }
  return null;
}
