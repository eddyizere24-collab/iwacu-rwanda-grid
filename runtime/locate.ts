/**
 * IWACU grid runtime — dependency-light locate()
 * Browser + Node. Lazy-loads per-district chunks via loader.
 */
export type VillageShare = { village_id: string; share: number; name?: string };
export type LocateResult = {
  finestLevel: "village" | "cell" | "sector" | "district" | "province" | "unknown";
  topVillages: VillageShare[];
  villagePct: number;
  cellPct: Record<string, number>;
  sectorPct: Record<string, number>;
  districtPct: Record<string, number>;
  provincePct: Record<string, number>;
  flags: string[];
  datasetVersion?: string;
  ms?: number;
};

export type DistrictChunk = {
  v: string;
  d: string;
  villages: Record<string, { n: string; c: string; s: string; d: string; p: string; lat: number; lon: number }>;
  cells: Array<{ g: string; p: number; b: number; t: Array<{ v: string; s: number }> }>;
};

export type Loader = (districtId: string) => Promise<DistrictChunk | null>;

const BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz";
export function encodeGeohash(lat: number, lon: number, precision: number): string {
  let idx = 0, bit = 0, even = true;
  let latMin = -90, latMax = 90, lonMin = -180, lonMax = 180;
  let geohash = "";
  while (geohash.length < precision) {
    if (even) {
      const mid = (lonMin + lonMax) / 2;
      if (lon >= mid) { idx = idx * 2 + 1; lonMin = mid; }
      else { idx = idx * 2; lonMax = mid; }
    } else {
      const mid = (latMin + latMax) / 2;
      if (lat >= mid) { idx = idx * 2 + 1; latMin = mid; }
      else { idx = idx * 2; latMax = mid; }
    }
    even = !even;
    if (++bit === 5) { geohash += BASE32[idx]; bit = 0; idx = 0; }
  }
  return geohash;
}

function haversineM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000;
  const toR = Math.PI / 180;
  const dLat = (lat2 - lat1) * toR;
  const dLon = (lon2 - lon1) * toR;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * toR) * Math.cos(lat2 * toR) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function nearbyHashes(lat: number, lon: number, precision: number, radiusM: number): string[] {
  const set = new Set<string>();
  set.add(encodeGeohash(lat, lon, precision));
  const dLat = radiusM / 111320;
  const dLon = radiusM / (111320 * Math.cos((lat * Math.PI) / 180) || 1);
  const steps = Math.max(1, Math.ceil(radiusM / (precision >= 8 ? 20 : precision >= 7 ? 150 : 1200)));
  for (let i = -steps; i <= steps; i++) {
    for (let j = -steps; j <= steps; j++) {
      set.add(encodeGeohash(lat + (i / steps) * dLat, lon + (j / steps) * dLon, precision));
    }
  }
  return [...set];
}

export async function locate(
  lat: number,
  lng: number,
  accuracyMeters: number,
  opts: {
    loadDistrict: Loader;
    coarseGh6?: Record<string, string[]>;
    centroids?: Array<{ lat: number; lon: number; v: string; d: string }>;
  }
): Promise<LocateResult> {
  const t0 = typeof performance !== "undefined" ? performance.now() : Date.now();
  const flags: string[] = [];
  const acc = Math.max(5, accuracyMeters || 50);

  let districtIds: string[] = [];
  if (opts.coarseGh6) {
    const hashes = nearbyHashes(lat, lng, 6, Math.max(acc, 500));
    const s = new Set<string>();
    for (const h of hashes) {
      const ds = opts.coarseGh6[h];
      if (ds) ds.forEach((d) => s.add(d));
    }
    districtIds = [...s];
  }
  if (districtIds.length === 0 && opts.centroids) {
    const nearest = opts.centroids
      .map((c) => ({ ...c, dist: haversineM(lat, lng, c.lat, c.lon) }))
      .sort((a, b) => a.dist - b.dist)
      .slice(0, 5);
    districtIds = [...new Set(nearest.map((n) => n.d))];
    if (nearest[0] && nearest[0].dist > 2000) flags.push("far_from_land");
  }

  const chunks: DistrictChunk[] = [];
  for (const d of districtIds) {
    const ch = await opts.loadDistrict(d);
    if (ch) chunks.push(ch);
  }

  const villageVotes: Record<string, number> = {};
  const cellIndex = new Map<string, { t: Array<{ v: string; s: number }> }>();
  for (const ch of chunks) {
    for (const c of ch.cells) cellIndex.set(c.g, c);
  }

  const hashes = [
    ...nearbyHashes(lat, lng, 7, acc),
    ...(acc <= 50 ? nearbyHashes(lat, lng, 8, acc) : []),
  ];

  let hit = 0;
  for (const h of new Set(hashes)) {
    const c = cellIndex.get(h);
    if (!c) continue;
    hit++;
    for (const t of c.t) villageVotes[t.v] = (villageVotes[t.v] || 0) + t.s;
  }

  if (hit === 0) {
    flags.push("gap_or_outside_grid");
    let best: { v: string; dist: number } | null = null;
    for (const ch of chunks) {
      for (const [vid, meta] of Object.entries(ch.villages)) {
        const dist = haversineM(lat, lng, meta.lat, meta.lon);
        if (!best || dist < best.dist) best = { v: vid, dist };
      }
    }
    if (!best && opts.centroids) {
      for (const c of opts.centroids) {
        const dist = haversineM(lat, lng, c.lat, c.lon);
        if (!best || dist < best.dist) best = { v: c.v, dist };
      }
    }
    if (best) {
      villageVotes[best.v] = 1;
      flags.push("nearest_village");
      if (best.dist > 500) flags.push("near_water_or_gap");
    }
  }

  const total = Object.values(villageVotes).reduce((a, b) => a + b, 0) || 1;
  const ranked = Object.entries(villageVotes)
    .map(([v, s]) => ({ village_id: v, share: s / total, name: undefined as string | undefined }))
    .sort((a, b) => b.share - a.share);

  const metaOf = (vid: string) => {
    for (const ch of chunks) if (ch.villages[vid]) return ch.villages[vid];
    return null;
  };
  const cellPct: Record<string, number> = {};
  const sectorPct: Record<string, number> = {};
  const districtPct: Record<string, number> = {};
  const provincePct: Record<string, number> = {};
  for (const r of ranked) {
    const m = metaOf(r.village_id);
    if (!m) continue;
    r.name = m.n;
    cellPct[m.c] = (cellPct[m.c] || 0) + r.share;
    sectorPct[m.s] = (sectorPct[m.s] || 0) + r.share;
    districtPct[m.d] = (districtPct[m.d] || 0) + r.share;
    provincePct[m.p] = (provincePct[m.p] || 0) + r.share;
  }

  const top1 = ranked[0]?.share || 0;
  let finestLevel: LocateResult["finestLevel"] = "unknown";
  if (top1 >= 0.55 && acc <= 500) finestLevel = "village";
  else if (Object.values(cellPct).some((x) => x >= 0.55)) finestLevel = "cell";
  else if (Object.values(sectorPct).some((x) => x >= 0.55)) finestLevel = "sector";
  else if (Object.values(districtPct).some((x) => x >= 0.55)) finestLevel = "district";
  else if (Object.values(provincePct).some((x) => x >= 0.55)) finestLevel = "province";
  else if (ranked.length) finestLevel = acc > 5000 ? "district" : "cell";

  const t1 = typeof performance !== "undefined" ? performance.now() : Date.now();
  return {
    finestLevel,
    topVillages: ranked.slice(0, 5).map((r) => ({
      village_id: r.village_id,
      share: Math.round(r.share * 1000) / 10,
      name: r.name,
    })),
    villagePct: Math.round(top1 * 1000) / 10,
    cellPct: Object.fromEntries(Object.entries(cellPct).map(([k, v]) => [k, Math.round(v * 1000) / 10])),
    sectorPct: Object.fromEntries(Object.entries(sectorPct).map(([k, v]) => [k, Math.round(v * 1000) / 10])),
    districtPct: Object.fromEntries(Object.entries(districtPct).map(([k, v]) => [k, Math.round(v * 1000) / 10])),
    provincePct: Object.fromEntries(Object.entries(provincePct).map(([k, v]) => [k, Math.round(v * 1000) / 10])),
    flags,
    datasetVersion: chunks[0]?.v,
    ms: Math.round((t1 - t0) * 10) / 10,
  };
}
