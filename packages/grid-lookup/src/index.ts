import { encode } from "./geohash.js";
import { readIrg2, longestPrefix, type CellInfo } from "./irg2.js";

export type LocateResult = {
  village_code: string | null;
  level: number | null;
  pure: boolean | null;
  key: string | null;
};

export type VillageMeta = {
  id: string;
  n?: string;
  c?: string;
  s?: string;
  d?: string;
  p?: string;
};

export type GridIndex = {
  vidOrder: string[];
  villages: Record<string, VillageMeta>;
  cells: Map<string, CellInfo>;
  baseUrl?: string;
};

function gunzipSyncNode(buf: Uint8Array): Uint8Array {
  // dynamic require for node only
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const zlib = require("node:zlib") as typeof import("node:zlib");
  return zlib.gunzipSync(Buffer.from(buf));
}

async function gunzipBrowser(buf: Uint8Array): Promise<Uint8Array> {
  const ds = new DecompressionStream("gzip");
  const stream = new Blob([buf]).stream().pipeThrough(ds);
  const ab = await new Response(stream).arrayBuffer();
  return new Uint8Array(ab);
}

async function gunzip(buf: Uint8Array): Promise<Uint8Array> {
  if (typeof process !== "undefined" && process.versions?.node) {
    return gunzipSyncNode(buf);
  }
  return gunzipBrowser(buf);
}

function parseRootPayload(raw: Uint8Array): {
  meta: { vid_order: string[]; villages: Record<string, VillageMeta> };
  bin: Uint8Array;
} {
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  const jlen = view.getUint32(0, false);
  const jsonBytes = raw.subarray(4, 4 + jlen);
  const meta = JSON.parse(new TextDecoder().decode(jsonBytes));
  const bin = raw.subarray(4 + jlen);
  return { meta, bin };
}

export async function loadRootFromBytes(gz: Uint8Array): Promise<GridIndex> {
  const raw = await gunzip(gz);
  const { meta, bin } = parseRootPayload(raw);
  const vidOrder: string[] = meta.vid_order || Object.keys(meta.villages || {});
  const cells = readIrg2(bin, vidOrder);
  return { vidOrder, villages: meta.villages || {}, cells };
}

export async function loadRootFile(path: string): Promise<GridIndex> {
  const fs = await import("node:fs/promises");
  const buf = await fs.readFile(path);
  return loadRootFromBytes(new Uint8Array(buf));
}

export async function loadGh6FromBytes(
  gz: Uint8Array,
  vidOrder: string[],
  into: Map<string, CellInfo>
): Promise<void> {
  const raw = await gunzip(gz);
  const cells = readIrg2(raw, vidOrder);
  for (const [k, v] of cells) into.set(k, v);
}

export type LocateOptions = {
  /** Browser/Node fetch base for gh6/{prefix}.bin.gz */
  baseUrl?: string;
  /** Node directory containing root.bin.gz and gh6/ */
  outDir?: string;
};

export async function locate(
  index: GridIndex,
  lat: number,
  lng: number,
  opts: LocateOptions = {}
): Promise<LocateResult> {
  const gh9 = encode(lat, lng, 9);
  const prefix6 = gh9.slice(0, 6);
  // lazy-load gh6 if not present
  let hasPrefix = false;
  for (const k of index.cells.keys()) {
    if (k.startsWith(prefix6) || prefix6.startsWith(k)) {
      hasPrefix = true;
      break;
    }
  }
  if (!hasPrefix) {
    if (opts.outDir) {
      const fs = await import("node:fs/promises");
      const path = `${opts.outDir}/gh6/${prefix6}.bin.gz`;
      try {
        const buf = await fs.readFile(path);
        await loadGh6FromBytes(new Uint8Array(buf), index.vidOrder, index.cells);
      } catch {
        /* missing chunk */
      }
    } else if (opts.baseUrl || index.baseUrl) {
      const base = (opts.baseUrl || index.baseUrl || "").replace(/\/$/, "");
      try {
        const res = await fetch(`${base}/gh6/${prefix6}.bin.gz`);
        if (res.ok) {
          const ab = await res.arrayBuffer();
          await loadGh6FromBytes(new Uint8Array(ab), index.vidOrder, index.cells);
        }
      } catch {
        /* network */
      }
    }
  }
  const hit = longestPrefix(gh9, index.cells);
  if (!hit) return { village_code: null, level: null, pure: null, key: null };
  const top = hit.info.shares[0]?.v ?? null;
  return {
    village_code: top,
    level: hit.info.prec,
    pure: hit.info.pure,
    key: hit.key,
  };
}

export { encode, readIrg2, longestPrefix };
