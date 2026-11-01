/**
 * Offline hierarchical locate over IRG2 grid.
 * CHANGED 2026-11-01 GROK: implements WORK ORDER algorithm; design in docs/HANDOFF.md
 */
import { encode, locate as gridLocate, type GridIndex, loadRootFile } from "../../grid-lookup/dist/index.js";

export const TAU = 0.8;

export type OfflineResult = {
  level: "village" | "akagari" | "umurenge" | "akarere" | "intara" | null;
  path: {
    village?: { code: string; name?: string; p: number };
    cell?: { code: string; name?: string; p: number };
    sector?: { code: string; name?: string; p: number };
    district?: { code: string; name?: string; p: number };
    province?: { code: string; name?: string; p: number };
  };
  per_level_candidates: Record<string, { code: string; name?: string; p: number }[]>;
  top3_villages: { code: string; name?: string; p: number }[];
  outside: boolean;
  tau: number;
  sigma: number;
};

function haversine_m(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000;
  const toR = Math.PI / 180;
  const dLat = (lat2 - lat1) * toR;
  const dLon = (lon2 - lon1) * toR;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * toR) * Math.cos(lat2 * toR) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function precisionForSigma(sigma: number): number {
  if (sigma <= 450) return 7;
  if (sigma <= 1800) return 6;
  return 5;
}

/** Decode geohash centre approximately via successive bisection (matches encode). */
function decodeCentre(gh: string): { lat: number; lon: number } {
  let latMin = -90,
    latMax = 90,
    lonMin = -180,
    lonMax = 180;
  let even = true;
  const BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz";
  for (const c of gh) {
    const idx = BASE32.indexOf(c);
    for (let mask = 16; mask > 0; mask >>= 1) {
      if (even) {
        const mid = (lonMin + lonMax) / 2;
        if (idx & mask) lonMin = mid;
        else lonMax = mid;
      } else {
        const mid = (latMin + latMax) / 2;
        if (idx & mask) latMin = mid;
        else latMax = mid;
      }
      even = !even;
    }
  }
  return { lat: (latMin + latMax) / 2, lon: (lonMin + lonMax) / 2 };
}

export type OutsideChecker = (lat: number, lng: number) => boolean;

export async function offlineLocate(
  index: GridIndex,
  lat: number,
  lng: number,
  accuracy_m: number,
  opts: { outDir?: string; baseUrl?: string; isOutside?: OutsideChecker; tau?: number } = {}
): Promise<OfflineResult> {
  const tau = opts.tau ?? TAU;
  const sigma = accuracy_m <= 10 ? 0 : accuracy_m / 1.51;
  const outside = opts.isOutside ? opts.isOutside(lat, lng) : false;
  if (outside) {
    return {
      level: null,
      path: {},
      per_level_candidates: {},
      top3_villages: [],
      outside: true,
      tau,
      sigma,
    };
  }

  // Fine path: longest-prefix IRG2
  if (sigma <= 15) {
    const hit = await gridLocate(index, lat, lng, { outDir: opts.outDir, baseUrl: opts.baseUrl });
    const code = hit.village_code;
    const meta = code ? index.villages[code] : undefined;
    const p = 1;
    const top = code ? [{ code, name: meta?.n, p }] : [];
    const path: OfflineResult["path"] = {};
    if (code && meta) {
      path.village = { code, name: meta.n, p };
      if (meta.c) path.cell = { code: meta.c, p };
      if (meta.s) path.sector = { code: meta.s, p };
      if (meta.d) path.district = { code: meta.d, p };
      if (meta.p) path.province = { code: meta.p, p };
    }
    return {
      level: code ? "village" : path.province ? "intara" : null,
      path,
      per_level_candidates: { village: top },
      top3_villages: top,
      outside: false,
      tau,
      sigma,
    };
  }

  // Gaussian over centres of precision-p cells within 3*sigma
  const p = precisionForSigma(sigma);
  // Neighbour enumeration via offset grid around point
  const villageMass = new Map<string, number>();
  let wsum = 0;
  // Sample a ring of geohashes around the point by scanning small lat/lng steps
  const step = p >= 7 ? 0.001 : p === 6 ? 0.004 : 0.015;
  const reach = (3 * Math.max(sigma, 1)) / 111320;
  for (let dlat = -reach; dlat <= reach; dlat += step) {
    for (let dlng = -reach; dlng <= reach; dlng += step) {
      const la = lat + dlat;
      const lo = lng + dlng;
      const gh = encode(la, lo, p);
      const centre = decodeCentre(gh);
      const d = haversine_m(lat, lng, centre.lat, centre.lon);
      if (d > 3 * Math.max(sigma, 1e-6)) continue;
      const w = Math.exp(-(d * d) / (2 * Math.max(sigma, 1e-6) ** 2));
      if (w < 1e-12) continue;
      // resolve cell via longest prefix after ensuring chunk load
      const hit = await gridLocate(index, centre.lat, centre.lon, {
        outDir: opts.outDir,
        baseUrl: opts.baseUrl,
      });
      if (!hit.village_code) continue;
      // For pure cells mass goes fully to that village; mixed would need shares from index
      villageMass.set(hit.village_code, (villageMass.get(hit.village_code) || 0) + w);
      wsum += w;
    }
  }

  if (wsum <= 0) {
    // fallback single lookup
    const hit = await gridLocate(index, lat, lng, { outDir: opts.outDir, baseUrl: opts.baseUrl });
    if (hit.village_code) {
      villageMass.set(hit.village_code, 1);
      wsum = 1;
    }
  }

  const villages: { code: string; name?: string; p: number }[] = [];
  for (const [code, mass] of villageMass) {
    villages.push({ code, name: index.villages[code]?.n, p: mass / wsum });
  }
  villages.sort((a, b) => b.p - a.p);
  const top3 = villages.slice(0, 3);

  // Aggregate hierarchy
  const agg = (key: "c" | "s" | "d" | "p") => {
    const m = new Map<string, number>();
    for (const v of villages) {
      const meta = index.villages[v.code];
      const code = meta?.[key];
      if (!code) continue;
      m.set(code, (m.get(code) || 0) + v.p);
    }
    return [...m.entries()]
      .map(([code, p]) => ({ code, p }))
      .sort((a, b) => b.p - a.p);
  };
  const cells = agg("c");
  const sectors = agg("s");
  const districts = agg("d");
  const provinces = agg("p");

  const pickLevel = (): OfflineResult["level"] => {
    if (villages[0] && villages[0].p >= tau) return "village";
    if (cells[0] && cells[0].p >= tau) return "akagari";
    if (sectors[0] && sectors[0].p >= tau) return "umurenge";
    if (districts[0] && districts[0].p >= tau) return "akarere";
    if (provinces[0]) return "intara";
    return null;
  };
  const level = pickLevel();
  const path: OfflineResult["path"] = {};
  if (villages[0]) path.village = villages[0];
  if (cells[0]) path.cell = cells[0];
  if (sectors[0]) path.sector = sectors[0];
  if (districts[0]) path.district = districts[0];
  if (provinces[0]) path.province = provinces[0];

  return {
    level,
    path,
    per_level_candidates: {
      village: villages.slice(0, 5),
      akagari: cells.slice(0, 5),
      umurenge: sectors.slice(0, 5),
      akarere: districts.slice(0, 5),
      intara: provinces.slice(0, 5),
    },
    top3_villages: top3,
    outside: false,
    tau,
    sigma,
  };
}

export { loadRootFile, type GridIndex };
