// CHANGED 2026-11-02 CLAUDE: fits the national calibration on SEED-TUNE (424242) rows and reports the
// expected calibration error (ECE) on the untouched SEED-TEST (20261030) rows, before and after calibration.
// Input: a directory holding the p4-national-<seed>.json files (rows[] with level_metrics).
// Output: calibration-v2.json (same shape as src/lib/calibration-v1.json) and p4-calibration-report.json.
// Nothing here changes the application; wiring calibration-v2.json into src/lib is a separate, reviewed step.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import {
  LEVELS, SEED_TEST, SEED_TUNE,
  calibrationForRows, expectedCalibrationError, lookupCalibration, readObservationArtifacts, tuneTau,
} from "./fit-calibration.mjs";

export const ECE_TARGET = 0.05;

function metric(row, level) {
  const m = row.level_metrics?.[level];
  if (!m || !m.top1_scope_code) return null;
  const score = Number(m.raw_score);
  return Number.isFinite(score) ? { score: Math.min(1, Math.max(0, score)), correct: Boolean(m.top1_correct) } : null;
}

export function buildCalibration(rows) {
  const tuneRows = rows.filter((row) => Number(row.seed) === SEED_TUNE && row.status === "success");
  if (!tuneRows.length) throw new Error("No successful SEED-TUNE rows (seed " + SEED_TUNE + ").");
  const levels = calibrationForRows(tuneRows);
  const tuned = tuneTau(rows, levels);
  const calibration = {
    version: "isotonic-v2-national",
    tau: tuned.tau,
    training_seed: SEED_TUNE,
    training_observations: tuneRows.length,
    tune_radius_max_m: 5000,
    target_accuracy: 0.92,
    tune_accuracy: tuned.accuracy,
    tune_target_met: tuned.target_met,
    levels,
  };
  const report = { seed_tune: SEED_TUNE, seed_test: SEED_TEST, ece_target: ECE_TARGET, tau: tuned.tau,
    tune_accuracy: tuned.accuracy, tune_target_met: tuned.target_met, levels: {} };
  const testRows = rows.filter((row) => Number(row.seed) === SEED_TEST && row.status === "success");
  for (const level of LEVELS) {
    const before = [], after = [];
    for (const row of testRows) {
      const m = metric(row, level);
      if (!m) continue;
      before.push({ probability: m.score, correct: m.correct });
      after.push({ probability: lookupCalibration(m.score, levels[level]), correct: m.correct });
    }
    const eceBefore = expectedCalibrationError(before);
    const eceAfter = expectedCalibrationError(after);
    report.levels[level] = {
      n_test: before.length,
      ece_raw: eceBefore === null ? null : Number(eceBefore.toFixed(4)),
      ece_calibrated: eceAfter === null ? null : Number(eceAfter.toFixed(4)),
      meets_target: eceAfter !== null && eceAfter <= ECE_TARGET,
    };
  }
  report.all_levels_meet_target = LEVELS.every((level) => report.levels[level].n_test === 0 || report.levels[level].meets_target);
  return { calibration, report };
}

async function main(argv) {
  const input = argv[0] || "/tmp/p4-in";
  const output = argv[1] || "/tmp/p4-calibration";
  const rows = readObservationArtifacts(input);
  const { calibration, report } = buildCalibration(rows);
  fs.mkdirSync(output, { recursive: true });
  fs.writeFileSync(path.join(output, "calibration-v2.json"), JSON.stringify(calibration, null, 2) + "\n");
  fs.writeFileSync(path.join(output, "p4-calibration-report.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report, null, 2));
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main(process.argv.slice(2)).catch((error) => {
    console.error(error?.stack || error);
    process.exitCode = 1;
  });
}
