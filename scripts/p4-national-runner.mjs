// CHANGED 2026-11-02 CLAUDE: low-load national validation runner against PRODUCTION /api/locate.
// Reads truth points from a CSV (NO database access), one request at a time, >= 2.2 s apart (the production
// limiter allows 30 requests/minute per IP), auto-stops on trouble, runs only at night (22:00-06:00 Kigali).
// Output rows use the same shape as scripts/w2-run-district.mjs so scripts/fit-calibration.mjs can read them.
// See docs/HANDOFF.md.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

export const RADII = [0, 100, 500, 2000];
export const LEVELS = ["village", "cell", "sector", "district", "province"];
export const MIN_GAP_MS = 2200;
export const WINDOW = 50;
export const ERROR_RATE_STOP = 0.05;
export const P95_STOP_MS = 3000;
export const CONSECUTIVE_5XX_STOP = 5;
const INFO_LEVELS = {
  0: new Set(["village"]),
  100: new Set(["village", "cell"]),
  500: new Set(["village", "cell", "sector"]),
  2000: new Set(["village", "cell", "sector", "district"]),
};

/** Night window: 22:00-06:00 Kigali (UTC+2) = 20:00-04:00 UTC. */
export function nightWindowOk(date = new Date()) {
  const hour = date.getUTCHours();
  return hour >= 20 || hour < 4;
}

export function parseCsv(text) {
  const lines = String(text).split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length < 2) throw new Error("CSV has no data rows.");
  const clean = (cell) => cell.trim().replace(/^"|"$/g, "");
  const header = lines[0].split(",").map(clean);
  for (const required of ["district_scope_code", "seed", "idx", "lng", "lat", "true_village_scope_code"]) {
    if (!header.includes(required)) throw new Error("CSV column missing: " + required);
  }
  return lines.slice(1).map((line, lineIndex) => {
    const cells = line.split(",").map(clean);
    const row = Object.fromEntries(header.map((name, index) => [name, cells[index] ?? ""]));
    const point = {
      district_scope_code: row.district_scope_code,
      seed: Number(row.seed),
      idx: Number(row.idx),
      longitude: Number(row.lng),
      latitude: Number(row.lat),
      true_village_scope_code: row.true_village_scope_code,
      kind: row.kind || "interior",
    };
    if (!Number.isFinite(point.seed) || !Number.isFinite(point.idx)) throw new Error("Bad seed/idx on CSV line " + (lineIndex + 2));
    if (!(point.latitude > -3.2 && point.latitude < -0.8 && point.longitude > 28.5 && point.longitude < 31.2)) {
      throw new Error("Point outside the Rwanda bounding box on CSV line " + (lineIndex + 2));
    }
    if (point.true_village_scope_code.split("-").length !== 6) throw new Error("Bad village scope code on CSV line " + (lineIndex + 2));
    return point;
  });
}

function mulberry32(seed) {
  let value = seed >>> 0;
  return () => {
    value = (value + 0x6D2B79F5) >>> 0;
    let t = value;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function stableSeed(seed, index, radius, district) {
  let hash = seed >>> 0;
  for (const char of district) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619) >>> 0;
  hash = (hash ^ Math.imul(index + 1, 0x9E3779B1)) >>> 0;
  hash = (hash ^ Math.imul(radius + 1, 0x85EBCA6B)) >>> 0;
  return hash;
}

export function applyNoise(point, radius, seed) {
  if (radius === 0) return { longitude: point.longitude, latitude: point.latitude };
  const random = mulberry32(stableSeed(seed, point.idx, radius, point.district_scope_code));
  const bearing = random() * Math.PI * 2;
  const metersPerLongitudeDegree = 111320 * Math.cos(point.latitude * Math.PI / 180);
  return {
    longitude: point.longitude + (Math.cos(bearing) * radius) / metersPerLongitudeDegree,
    latitude: point.latitude + (Math.sin(bearing) * radius) / 110574,
  };
}

export function prefixCodes(villageCode) {
  const parts = String(villageCode).split("-");
  if (parts.length !== 6) throw new Error("Invalid village scope code: " + villageCode);
  return {
    province: parts.slice(0, 2).join("-"),
    district: parts.slice(0, 3).join("-"),
    sector: parts.slice(0, 4).join("-"),
    cell: parts.slice(0, 5).join("-"),
    village: parts.join("-"),
  };
}

/** Round-robin over districts so that an early stop still covers every district. */
export function buildPlan(points, seed, radii = RADII) {
  const byDistrict = new Map();
  for (const point of points.filter((item) => item.seed === seed)) {
    if (!byDistrict.has(point.district_scope_code)) byDistrict.set(point.district_scope_code, []);
    byDistrict.get(point.district_scope_code).push(point);
  }
  const districts = [...byDistrict.keys()].sort();
  for (const list of byDistrict.values()) list.sort((a, b) => (a.kind === b.kind ? a.idx - b.idx : a.kind < b.kind ? -1 : 1));
  const longest = Math.max(0, ...[...byDistrict.values()].map((list) => list.length));
  const plan = [];
  for (let ordinal = 0; ordinal < longest; ordinal += 1) {
    for (const district of districts) {
      const point = byDistrict.get(district)[ordinal];
      if (!point) continue;
      for (const radius of radii) plan.push({ point, radius, seed });
    }
  }
  return plan;
}

function isErrorResponse(httpStatus, response, transportError) {
  if (transportError || httpStatus !== 200 || !response) return true;
  const flags = Array.isArray(response.flags) ? response.flags : [];
  return response.status === "error" || response.degraded === true || response.source === "prior" ||
    flags.includes("degraded") || flags.includes("rwanda_classifier_unavailable");
}

export function compactObservation(item, response, httpStatus, latencyMs, transportError) {
  const { point, radius, seed } = item;
  const truth = prefixCodes(point.true_village_scope_code);
  const success = response && response.status === "success";
  const level = success ? response.level || null : null;
  const chosen = level && response.hierarchy ? response.hierarchy[level]?.scope_code || null : null;
  const candidatesByLevel = response?.per_level_candidates || response?.hierarchyCandidates || {};
  const levelMetrics = {};
  for (const candidateLevel of LEVELS) {
    const candidates = Array.isArray(candidatesByLevel[candidateLevel]) ? candidatesByLevel[candidateLevel] : [];
    const top = candidates[0];
    const score = Math.max(0, Math.min(100, Number(top?.confidence) || 0));
    levelMetrics[candidateLevel] = {
      raw_score: Number.isFinite(Number(top?.raw_score)) ? Number(top.raw_score) : score / 100,
      calibrated_probability: top?.calibrated_probability !== null && top?.calibrated_probability !== undefined &&
        Number.isFinite(Number(top.calibrated_probability)) ? Number(top.calibrated_probability) : null,
      top1_scope_code: top?.scope_code || null,
      top1_correct: Boolean(top?.scope_code && top.scope_code === truth[candidateLevel]),
    };
  }
  const flags = Array.isArray(response?.flags) ? response.flags : [];
  const top3 = Array.isArray(response?.top3_villages) ? response.top3_villages : [];
  return {
    district_code: point.district_scope_code,
    sample_kind: point.kind,
    sample_index: point.idx,
    seed,
    radius_m: radius,
    true_village_scope_code: point.true_village_scope_code,
    true_prefixes: truth,
    status: response?.status || "transport_error",
    http_status: httpStatus,
    latency_ms: latencyMs,
    error: isErrorResponse(httpStatus, response, transportError),
    transport_error: transportError || null,
    chosen_level: level || (response?.status === "outside" ? "outside" : "empty"),
    chosen_scope_code: chosen,
    chosen_level_correct: Boolean(chosen && level && chosen === truth[level]),
    empty: !response || response.status === "error" || (success && (!level || !chosen)),
    outside_rwanda: Boolean(response?.outside_rwanda || response?.status === "outside" || flags.includes("outside_rwanda")),
    flags,
    village_top1_correct: levelMetrics.village.top1_correct,
    village_top3_correct: top3.some((candidate) => candidate?.scope_code === truth.village),
    level_metrics: levelMetrics,
    calibration_version: response?.calibration_version || null,
    response_commit_sha: response?.commit_sha || null,
  };
}

function percentile(sorted, p) {
  return sorted.length ? sorted[Math.max(0, Math.ceil(p * sorted.length) - 1)] : null;
}

/** Returns a stop reason or null. `recent` holds the most recent observations (any length). */
export function stopReason(recent, consecutive5xx) {
  if (recent.some((row) => row.http_status === 429)) return "http_429";
  if (consecutive5xx >= CONSECUTIVE_5XX_STOP) return "consecutive_5xx";
  if (recent.length >= WINDOW) {
    const window = recent.slice(-WINDOW);
    const errorRate = window.filter((row) => row.error).length / window.length;
    if (errorRate > ERROR_RATE_STOP) return "error_rate_over_5pct_in_last_50";
    const sorted = window.map((row) => row.latency_ms).sort((a, b) => a - b);
    if (percentile(sorted, 0.95) > P95_STOP_MS) return "p95_over_3000ms_in_last_50";
  }
  return null;
}

export function summarize(rows) {
  const groups = {};
  const add = (name, row) => {
    const group = (groups[name] ||= []);
    group.push(row);
  };
  for (const row of rows) {
    add("radius_" + row.radius_m, row);
    add("province_" + row.true_prefixes.province, row);
    add("kind_" + row.sample_kind, row);
    add("all", row);
  }
  const out = {};
  for (const [name, list] of Object.entries(groups)) {
    const sorted = list.map((row) => row.latency_ms).sort((a, b) => a - b);
    const informative = list.filter((row) => INFO_LEVELS[row.radius_m]?.has(row.chosen_level)).length;
    out[name] = {
      n: list.length,
      village_correct_pct: Number((100 * list.filter((row) => row.village_top1_correct).length / list.length).toFixed(2)),
      chosen_level_correct_pct: Number((100 * list.filter((row) => row.chosen_level_correct).length / list.length).toFixed(2)),
      informative_pct: Number((100 * informative / list.length).toFixed(2)),
      errors: list.filter((row) => row.error).length,
      empty: list.filter((row) => row.empty).length,
      p50_ms: percentile(sorted, 0.5),
      p95_ms: percentile(sorted, 0.95),
    };
  }
  return out;
}

export async function runPlan({ plan, baseUrl, gapMs, fetchImpl = fetch, sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  now = () => Date.now(), onFlush = () => {}, flushEvery = 100 }) {
  const rows = [];
  let consecutive5xx = 0;
  let previousStart = 0;
  let stop = null;
  for (const item of plan) {
    const wait = Math.max(0, previousStart + gapMs - now());
    if (wait) await sleep(wait);
    const started = now();
    previousStart = started;
    const noisy = applyNoise(item.point, item.radius, item.seed);
    let httpStatus = 0, response = null, transportError = null;
    try {
      const reply = await fetchImpl(baseUrl.replace(/\/+$/, "") + "/api/locate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ latitude: noisy.latitude, longitude: noisy.longitude, accuracy: item.radius, method: "gps" }),
        signal: AbortSignal.timeout(12000),
      });
      httpStatus = reply.status;
      try { response = await reply.json(); } catch { response = null; }
    } catch (caught) {
      transportError = caught instanceof Error ? caught.message : String(caught);
    }
    const row = compactObservation(item, response, httpStatus, now() - started, transportError);
    rows.push(row);
    consecutive5xx = httpStatus >= 500 ? consecutive5xx + 1 : 0;
    if (rows.length % flushEvery === 0) onFlush(rows, null);
    stop = stopReason(rows.slice(-WINDOW), consecutive5xx);
    if (stop) break;
  }
  return { rows, outcome: stop ? "AUTO_STOPPED" : "COMPLETED", stop_reason: stop };
}

function writeAtomic(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = file + ".tmp";
  fs.writeFileSync(temp, text);
  fs.renameSync(temp, file);
}

export async function main(env = process.env, clock = () => new Date()) {
  const seed = Number(env.P4_SEED);
  if (![424242, 20261030].includes(seed)) throw new Error("P4_SEED must be 424242 or 20261030.");
  const baseUrl = env.P4_BASE_URL || "https://iwacu-rwanda-2.vercel.app";
  const outDir = env.P4_OUT || "/tmp/p4-out";
  const outFile = path.join(outDir, "p4-national-" + seed + ".json");
  const header = { workflow: "P4 national validation", seed, base_url: baseUrl, source_sha: env.GITHUB_SHA || "local",
    started_at: clock().toISOString() };
  if (!nightWindowOk(clock())) {
    writeAtomic(outFile, JSON.stringify({ ...header, outcome: "TOO_EARLY", reason: "Runs only 22:00-06:00 Kigali (20:00-04:00 UTC).", rows: [] }, null, 2) + "\n");
    console.error("TOO_EARLY: this validation runs only between 22:00 and 06:00 Kigali time.");
    return 4;
  }
  const points = parseCsv(fs.readFileSync(env.P4_CSV || "data/p4-truth-points.csv", "utf8"));
  const plan = buildPlan(points, seed);
  if (!plan.length) throw new Error("No plan rows for seed " + seed);
  const gapMs = Math.max(MIN_GAP_MS, Number(env.P4_GAP_MS) || MIN_GAP_MS);
  const finish = (rows, outcome, reason) => {
    const distinctShas = [...new Set(rows.map((row) => row.response_commit_sha).filter(Boolean))];
    writeAtomic(outFile, JSON.stringify({ ...header, finished_at: clock().toISOString(), planned: plan.length, completed: rows.length,
      outcome: outcome || "RUNNING", stop_reason: reason, gap_ms: gapMs, response_commit_shas: distinctShas,
      summary: rows.length ? summarize(rows) : {}, rows }) + "\n");
  };
  const result = await runPlan({ plan, baseUrl, gapMs, onFlush: (rows) => finish(rows, "RUNNING", null) });
  finish(result.rows, result.outcome, result.stop_reason);
  console.log(JSON.stringify({ seed, planned: plan.length, completed: result.rows.length, outcome: result.outcome,
    stop_reason: result.stop_reason, summary_all: summarize(result.rows).all }));
  return result.outcome === "COMPLETED" ? 0 : 3;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().then((code) => { process.exitCode = code; }).catch((error) => {
    console.error(error?.stack || error);
    process.exitCode = 1;
  });
}
