/**
 * IRG2 grid lookup (Node + browser).
 * CHANGED 2026-11-01 GROK: longest-prefix locate; see docs/HANDOFF.md
 */
import { encode } from "./geohash.js";
import { readIrg2, longestPrefix, type CellInfo } from "./irg2.js";

export type LocateResult = {
  village_code: string | null;
  level: number | null;
  pure: boolean | null;
  key: string | null;
};

export type VillageMeta = { id: string; n?: string; c?: string; s?: string; d?: string; p?: string };

export type GridIndex = {
  vidOrder: string[];
  villages: Record<string, VillageMeta>;
  cells: Map<string, CellInfo>;
  baseUrl?: string;
};

function gunzipSyncNode(buf: Uint8Array): Uint8Array {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const zlib = require("node:zlib") as typeof import("node:zlib");
  return new Uint8Array(zlib.gunzipSync(Buffer.from(buf)));
}

async function gunzip(buf: Uint8Array): Promise<Uint8Array> {
  if (typeof process !== "undefined" && process.versions?.node) return gunzipSyncNode(buf);
  const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
  const stream = new Blob([ab]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

function parseRootPayload(raw: Uint8Array) {
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  const jlen = view.getUint32(0, false);
  const meta = JSON.parse(new TextDecoder().decode(raw.subarray(4, 4 + jlen)));
  return { meta, bin: raw.subarray(4 + jlen) };
}

export async function loadRootFromBytes(gz: Uint8Array): Promise<GridIndex> {
  const raw = await gunzip(gz);
  const { meta, bin } = parseRootPayload(raw);
  const vidOrder: string[] = meta.vid_order || Object.keys(meta.villages || {});
  return { vidOrder, villages: meta.villages || {}, cells: readIrg2(bin, vidOrder) };
}

export async function loadRootFile(path: string): Promise<GridIndex> {
  const fs = await import("node:fs/promises");
  return loadRootFromBytes(new Uint8Array(await fs.readFile(path)));
}

export async function loadGh6FromBytes(
  gz: Uint8Array,
  vidOrder: string[],
  into: Map<string, CellInfo>
): Promise<void> {
  const cells = readIrg2(await gunzip(gz), vidOrder);
  for (const [k, v] of cells) into.set(k, v);
}

export async function locate(
  index: GridIndex,
  lat: number,
  lng: number,
  opts: { outDir?: string; baseUrl?: string } = {}
): Promise<LocateResult> {
  const gh9 = encode(lat, lng, 9);
  const prefix6 = gh9.slice(0, 6);
  let has = false;
  for (const k of index.cells.keys()) {
    if (k.startsWith(prefix6) || prefix6.startsWith(k)) {
      has = true;
      break;
    }
  }
  if (!has && opts.outDir) {
    try {
      const fs = await import("node:fs/promises");
      await loadGh6FromBytes(
        new Uint8Array(await fs.readFile(`${opts.outDir}/gh6/${prefix6}.bin.gz`)),
        index.vidOrder,
        index.cells
      );
    } catch {
      /* missing chunk */
    }
  }
  const hit = longestPrefix(gh9, index.cells);
  if (!hit) return { village_code: null, level: null, pure: null, key: null };
  return {
    village_code: hit.info.shares[0]?.v ?? null,
    level: hit.info.prec,
    pure: hit.info.pure,
    key: hit.key,
  };
}

export { encode, readIrg2, longestPrefix };
export type { CellInfo };
