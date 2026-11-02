// CHANGED 2026-11-02 CLAUDE: unit tests for the night runner and the calibration report (no network, no database).
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  buildPlan, compactObservation, main, nightWindowOk, parseCsv, runPlan, stopReason, summarize,
} from "./p4-national-runner.mjs";
import { buildCalibration } from "./p4-calibrate.mjs";

const CSV = [
  "district_scope_code,seed,idx,lng,lat,true_village_scope_code,kind",
  "RW-P1-D11,424242,1,30.0619,-1.9441,RW-P1-D11-S1101-C110101-V11010101,interior",
  "RW-P1-D11,424242,2,30.0550,-1.9520,RW-P1-D11-S1101-C110101-V11010102,shared_boundary_50m",
  "RW-P3-D37,424242,1,29.1000,-2.3000,RW-P3-D37-S3701-C370101-V37010101,interior",
  "RW-P3-D37,20261030,1,29.1100,-2.3100,RW-P3-D37-S3701-C370101-V37010102,interior",
].join("\n");

function okResponse(point) {
  const code = point.true_village_scope_code;
  const parts = code.split("-");
  const scope = (n) => parts.slice(0, n).join("-");
  const cand = (n, conf) => [{ scope_code: scope(n), confidence: conf, raw_score: conf / 100, calibrated_probability: conf / 100 }];
  return {
    status: "success", level: "village", source: "gps", flags: [], commit_sha: "abc",
    hierarchy: { village: { scope_code: code }, cell: { scope_code: scope(5) } },
    per_level_candidates: { village: cand(6, 80), cell: cand(5, 90), sector: cand(4, 95), district: cand(3, 99), province: cand(2, 100) },
    top3_villages: [{ scope_code: code }],
  };
}
const jsonReply = (status, body) => ({ status, json: async () => body });

test("night window is 22:00-06:00 Kigali (20:00-04:00 UTC)", () => {
  assert.equal(nightWindowOk(new Date("2026-11-02T19:59:00Z")), false);
  assert.equal(nightWindowOk(new Date("2026-11-02T20:00:00Z")), true);
  assert.equal(nightWindowOk(new Date("2026-11-03T03:59:00Z")), true);
  assert.equal(nightWindowOk(new Date("2026-11-03T04:00:00Z")), false);
  assert.equal(nightWindowOk(new Date("2026-11-02T06:00:00Z")), false);
});

test("CSV parsing validates columns, bounding box and village code", () => {
  const points = parseCsv(CSV);
  assert.equal(points.length, 4);
  assert.equal(points[1].kind, "shared_boundary_50m");
  assert.throws(() => parseCsv("a,b\n1,2"), /column missing/);
  assert.throws(() => parseCsv(CSV.replace("-1.9441", "10.0")), /bounding box/);
  assert.throws(() => parseCsv(CSV.replace("RW-P1-D11-S1101-C110101-V11010101", "RW-P1")), /village scope code/);
});

test("plan is round-robin over districts and covers the 4 radii", () => {
  const plan = buildPlan(parseCsv(CSV), 424242);
  assert.equal(plan.length, 3 * 4);
  assert.deepEqual(plan.slice(0, 8).map((item) => item.point.district_scope_code),
    ["RW-P1-D11", "RW-P1-D11", "RW-P1-D11", "RW-P1-D11", "RW-P3-D37", "RW-P3-D37", "RW-P3-D37", "RW-P3-D37"]);
  assert.deepEqual([...new Set(plan.map((item) => item.radius))], [0, 100, 500, 2000]);
  assert.equal(buildPlan(parseCsv(CSV), 20261030).length, 4);
});

test("a clean run completes, sends accuracy = radius and builds fit-calibration rows", async () => {
  const bodies = [];
  const plan = buildPlan(parseCsv(CSV), 424242);
  const fetchImpl = async (_url, init) => {
    const body = JSON.parse(init.body);
    bodies.push(body);
    const item = plan[bodies.length - 1];
    return jsonReply(200, okResponse(item.point));
  };
  const result = await runPlan({ plan, baseUrl: "https://example.test/", gapMs: 0, fetchImpl, sleep: async () => {} });
  assert.equal(result.outcome, "COMPLETED");
  assert.equal(result.rows.length, 12);
  assert.deepEqual(bodies.slice(0, 4).map((b) => b.accuracy), [0, 100, 500, 2000]);
  assert.equal(result.rows[0].village_top1_correct, true);
  assert.equal(result.rows[0].level_metrics.village.top1_correct, true);
  assert.equal(result.rows[0].error, false);
  const summary = summarize(result.rows);
  assert.equal(summary.all.n, 12);
  assert.equal(summary["radius_0"].village_correct_pct, 100);
  assert.ok(summary["province_RW-P1"] && summary["province_RW-P3"] && summary["kind_shared_boundary_50m"]);
});

test("a single HTTP 429 stops the run at once", async () => {
  const plan = buildPlan(parseCsv(CSV), 424242);
  let calls = 0;
  const fetchImpl = async () => { calls += 1; return calls === 3 ? jsonReply(429, { status: "error" }) : jsonReply(200, okResponse(plan[0].point)); };
  const result = await runPlan({ plan, baseUrl: "https://example.test", gapMs: 0, fetchImpl, sleep: async () => {} });
  assert.equal(result.outcome, "AUTO_STOPPED");
  assert.equal(result.stop_reason, "http_429");
  assert.equal(result.rows.length, 3);
});

test("five consecutive 5xx stop the run", async () => {
  const plan = buildPlan(parseCsv(CSV), 424242);
  const fetchImpl = async () => jsonReply(503, { status: "error" });
  const result = await runPlan({ plan, baseUrl: "https://example.test", gapMs: 0, fetchImpl, sleep: async () => {} });
  assert.equal(result.stop_reason, "consecutive_5xx");
  assert.equal(result.rows.length, 5);
});

test("more than 5% errors in 50 consecutive requests stop the run", () => {
  const good = { error: false, latency_ms: 100, http_status: 200 };
  const bad = { error: true, latency_ms: 100, http_status: 200 };
  assert.equal(stopReason(Array(47).fill(good).concat([bad, bad, good]), 0), null); // 2/50 = 4%
  assert.equal(stopReason(Array(46).fill(good).concat([bad, bad, bad, good]), 0), "error_rate_over_5pct_in_last_50"); // 3/50 = 6%
  assert.equal(stopReason(Array(49).fill(good), 0), null); // window not full
});

test("p95 above 3000 ms in the last 50 stops the run", () => {
  const slow = { error: false, latency_ms: 3500, http_status: 200 };
  const fast = { error: false, latency_ms: 200, http_status: 200 };
  assert.equal(stopReason(Array(45).fill(fast).concat(Array(5).fill(slow)), 0), "p95_over_3000ms_in_last_50");
  assert.equal(stopReason(Array(48).fill(fast).concat(Array(2).fill(slow)), 0), null);
});

test("degraded and prior answers count as errors", () => {
  const item = buildPlan(parseCsv(CSV), 424242)[0];
  const degraded = compactObservation(item, { status: "success", degraded: true, source: "prior", flags: ["degraded"] }, 200, 50, null);
  assert.equal(degraded.error, true);
  const transport = compactObservation(item, null, 0, 50, "timeout");
  assert.equal(transport.status, "transport_error");
  assert.equal(transport.error, true);
});

test("main refuses to run outside the night window and makes no request", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "p4-"));
  const code = await main({ P4_SEED: "424242", P4_OUT: dir, P4_CSV: path.join(dir, "none.csv") }, () => new Date("2026-11-02T10:00:00Z"));
  assert.equal(code, 4);
  const written = JSON.parse(fs.readFileSync(path.join(dir, "p4-national-424242.json"), "utf8"));
  assert.equal(written.outcome, "TOO_EARLY");
});

test("calibration report: isotonic fit on tune seed lowers ECE on the test seed", () => {
  let state = 12345;
  const random = () => { state = (state * 1664525 + 1013904223) >>> 0; return state / 4294967296; };
  const makeRows = (seed, n) => Array.from({ length: n }, () => {
    const score = 0.5 + 0.5 * random();            // the engine says 50-100 %
    const trueProbability = score * 0.6;            // but reality is 60 % of that (over-confident)
    const correct = random() < trueProbability;
    const metrics = {};
    for (const level of ["village", "cell", "sector", "district", "province"]) {
      metrics[level] = { raw_score: score, calibrated_probability: null, top1_scope_code: "X", top1_correct: correct };
    }
    return { seed, status: "success", radius_m: 100, level_metrics: metrics, true_prefixes: {} };
  });
  const rows = makeRows(424242, 3000).concat(makeRows(20261030, 3000)); // 3000 = 30 districts x 25 points x 4 radii
  const { calibration, report } = buildCalibration(rows);
  assert.equal(calibration.version, "isotonic-v2-national");
  assert.equal(report.levels.village.n_test, 3000);
  assert.ok(report.levels.village.ece_raw > 0.15, "raw ECE should be large: " + report.levels.village.ece_raw);
  assert.ok(report.levels.village.ece_calibrated <= 0.05, "calibrated ECE: " + report.levels.village.ece_calibrated);
  assert.equal(report.levels.village.meets_target, true);
  assert.throws(() => buildCalibration(makeRows(20261030, 10)), /SEED-TUNE/);
});
