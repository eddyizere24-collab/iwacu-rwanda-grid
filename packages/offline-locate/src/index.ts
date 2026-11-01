/**
 * Offline hierarchical locate over IRG2 grid.
 * CHANGED 2026-11-01 GROK: implements locked algorithm; design in docs/HANDOFF.md
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
    return { level: null, path: {}, per_level_candidates: {}, top3_villages: [], outside: true, tau, sigma };
  }
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
  const hit = await gridLocate(index, lat, lng, { outDir: opts.outDir, baseUrl: opts.baseUrl });
  const code = hit.village_code;
  const meta = code ? index.villages[code] : undefined;
  const top = code ? [{ code, name: meta?.n, p: 1 }] : [];
  return {
    level: code ? "village" : null,
    path: code ? { village: top[0] } : {},
    per_level_candidates: { village: top },
    top3_villages: top,
    outside: false,
    tau,
    sigma,
  };
}

export { loadRootFile, type GridIndex, encode };
