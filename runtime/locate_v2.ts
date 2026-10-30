/**
 * IWACU Gaussian-weighted geohash locate — algorithm lock 2026-10-30
 * sigma = a/1.51; weight exp(-d^2/(2*sigma^2)); tau=0.80; never empty.
 * Chunks: geohash-4 prefix. Summary pyramid for large sigma.
 */
export type VillageShare = { village_id: string; p: number; name?: string };
export type LocateResult = {
  finestLevel: "village" | "cell" | "sector" | "district" | "province" | "unknown";
  chosenId: string | null;
  chosenP: number;
  topVillages: VillageShare[];
  path: { province?: string; district?: string; sector?: string; cell?: string; village?: string };
  flags: string[];
  datasetVersion?: string;
  ms?: number;
  sigma?: number;
  precision?: number;
  kbDownloaded?: number;
};

const BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz";
export function encodeGeohash(lat: number, lon: number, precision: number): string {
  let idx = 0, bit = 0, even = true;
  let latMin = -90, latMax = 90, lonMin = -180, lonMax = 180;
  let geohash = "";
  while (geohash.length < precision) {
    if (even) {
      const mid = (lonMin + lonMax) / 2;
      if (lon >= mid) { idx = idx * 2 + 1; lonMin = mid; } else { idx = idx * 2; lonMax = mid; }
    } else {
      const mid = (latMin + latMax) / 2;
      if (lat >= mid) { idx = idx * 2 + 1; latMin = mid; } else { idx = idx * 2; latMax = mid; }
    }
    even = !even;
    if (++bit === 5) { geohash += BASE32[idx]; bit = 0; idx = 0; }
  }
  return geohash;
}

function decodeCenter(gh: string): [number, number] {
  let even = true;
  let latMin = -90, latMax = 90, lonMin = -180, lonMax = 180;
  for (const c of gh) {
    const idx = BASE32.indexOf(c);
    for (let mask = 16; mask > 0; mask >>= 1) {
      if (even) {
        const mid = (lonMin + lonMax) / 2;
        if (idx & mask) lonMin = mid; else lonMax = mid;
      } else {
        const mid = (latMin + latMax) / 2;
        if (idx & mask) latMin = mid; else latMax = mid;
      }
      even = !even;
    }
  }
  return [(latMin + latMax) / 2, (lonMin + lonMax) / 2];
}

function haversineM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000, p = Math.PI / 180;
  const a = Math.sin(((lat2 - lat1) * p) / 2) ** 2 +
    Math.cos(lat1 * p) * Math.cos(lat2 * p) * Math.sin(((lon2 - lon1) * p) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(Math.min(1, a)));
}

export type Chunk = {
  v: string;
  prefix: string;
  cells: Array<{ g: string; t: Array<{ v: string; s: number }> }>;
  villages: Record<string, { n: string; c: string; s: string; d: string; p: string; lat: number; lon: number }>;
};

export type Pyramid = {
  v: string;
  g5: Record<string, [Array<[string, number]>, ...Array<Array<[string, number]>>]>;
  bbox: { lat_min: number; lat_max: number; lon_min: number; lon_max: number };
};

export async function locate(
  lat: number,
  lng: number,
  accuracyMeters: number,
  opts: {
    loadChunk: (gh4: string) => Promise<Chunk | null>;
    pyramid?: Pyramid;
    tau?: number;
  }
): Promise<LocateResult> {
  const t0 = typeof performance !== "undefined" ? performance.now() : Date.now();
  const flags: string[] = [];
  const tau = opts.tau ?? 0.8;
  const a = Math.max(1, accuracyMeters || 50);
  let kb = 0;

  const bbox = opts.pyramid?.bbox;
  if (bbox && (lat < bbox.lat_min || lat > bbox.lat_max || lng < bbox.lon_min || lng > bbox.lon_max)) {
    flags.push("outside_rwanda");
    return {
      finestLevel: "unknown", chosenId: null, chosenP: 0, topVillages: [], path: {}, flags,
      ms: Math.round((typeof performance !== "undefined" ? performance.now() : Date.now()) - t0),
    };
  }

  const sigma = a <= 10 ? 1e-6 : a / 1.51;
  let precision = 7;
  if (sigma > 1800) precision = 5;
  else if (sigma > 450) precision = 6;

  const votes: Record<string, number> = {};
  let wsum = 0;
  const meta: Record<string, Chunk["villages"][string]> = {};

  if (precision >= 6) {
    const prefixes = new Set<string>();
    const stepM = precision === 7 ? 150 : 600;
    const n = Math.max(1, Math.ceil((3 * Math.max(sigma, 50)) / stepM));
    const dLat = stepM / 110574;
    const dLon = stepM / (111320 * Math.max(0.3, Math.abs(Math.cos((lat * Math.PI) / 180))));
    for (let i = -n; i <= n; i++) {
      for (let j = -n; j <= n; j++) {
        prefixes.add(encodeGeohash(lat + i * dLat, lng + j * dLon, 4));
      }
    }
    const cellMap = new Map<string, Array<{ v: string; s: number }>>();
    for (const pref of prefixes) {
      const ch = await opts.loadChunk(pref);
      if (!ch) continue;
      kb += 65;
      for (const c of ch.cells) cellMap.set(c.g, c.t);
      Object.assign(meta, ch.villages);
    }
    for (let i = -n; i <= n; i++) {
      for (let j = -n; j <= n; j++) {
        const la = lat + i * dLat;
        const lo = lng + j * dLon;
        const gh = encodeGeohash(la, lo, 7);
        const shares = cellMap.get(gh);
        if (!shares) continue;
        const [clat, clon] = decodeCenter(gh);
        const d = haversineM(lat, lng, clat, clon);
        if (d > 3 * Math.max(sigma, 1) + 80) continue;
        const w = sigma < 1e-5 ? 1 : Math.exp((-d * d) / (2 * sigma * sigma));
        wsum += w;
        for (const t of shares) votes[t.v] = (votes[t.v] || 0) + w * t.s;
      }
    }
  }

  if (wsum <= 0 && opts.pyramid) {
    const key = encodeGeohash(lat, lng, 5);
    const node = opts.pyramid.g5[key];
    if (node && node[0]) {
      for (const pair of node[0]) {
        const v = pair[0], s = pair[1];
        votes[v] = s;
      }
      wsum = Object.values(votes).reduce((a, b) => a + b, 0) || 1;
    }
  }

  if (wsum <= 0) {
    flags.push("nearest_fallback");
    votes["__unknown__"] = 1;
    wsum = 1;
  }

  const Pv = Object.fromEntries(Object.entries(votes).map(([v, s]) => [v, s / wsum]));
  const ranked = Object.entries(Pv).filter(([v]) => v !== "__unknown__").sort((a, b) => b[1] - a[1]);

  const Pc: Record<string, number> = {}, Ps: Record<string, number> = {}, Pd: Record<string, number> = {}, Pp: Record<string, number> = {};
  for (const [v, pr] of ranked) {
    const m = meta[v];
    if (!m) continue;
    Pc[m.c] = (Pc[m.c] || 0) + pr;
    Ps[m.s] = (Ps[m.s] || 0) + pr;
    Pd[m.d] = (Pd[m.d] || 0) + pr;
    Pp[m.p] = (Pp[m.p] || 0) + pr;
  }
  const top1 = (o: Record<string, number>) => {
    let best = 0, id: string | null = null;
    for (const [k, v] of Object.entries(o)) if (v > best) { best = v; id = k; }
    return { p: best, id };
  };

  const levels: Array<{ level: LocateResult["finestLevel"]; p: number; id: string | null }> = [
    { level: "village", p: ranked[0]?.[1] || 0, id: ranked[0]?.[0] || null },
    { level: "cell", ...top1(Pc) },
    { level: "sector", ...top1(Ps) },
    { level: "district", ...top1(Pd) },
    { level: "province", ...top1(Pp) },
  ];
  let chosen = levels[levels.length - 1];
  for (const L of levels) {
    if (L.p >= tau) { chosen = L; break; }
  }

  const topVillages = ranked.slice(0, 3).map(([v, pr]) => ({
    village_id: v, p: Math.round(pr * 1000) / 10, name: meta[v]?.n,
  }));
  const topMeta = ranked[0] ? meta[ranked[0][0]] : null;
  const path = topMeta
    ? { province: topMeta.p, district: topMeta.d, sector: topMeta.s, cell: topMeta.c, village: ranked[0][0] }
    : {};

  if (topVillages.length === 0) {
    flags.push("empty_prevented");
    topVillages.push({ village_id: "unknown", p: 0, name: "hafi" });
  }

  const t1 = typeof performance !== "undefined" ? performance.now() : Date.now();
  return {
    finestLevel: chosen.level,
    chosenId: chosen.id,
    chosenP: Math.round(chosen.p * 1000) / 10,
    topVillages,
    path,
    flags,
    sigma: a <= 10 ? 0 : a / 1.51,
    precision,
    ms: Math.round((t1 - t0) * 10) / 10,
    kbDownloaded: kb,
  };
}
