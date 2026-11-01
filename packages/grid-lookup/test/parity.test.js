/**
 * Parity tests expect fixtures/parity.jsonl.gz produced by Python decoder
 * (100k points: lat,lng,key,village). Skip if missing.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";
import { encode, longestPrefix, readIrg2 } from "../dist/irg2.js";
import { loadRootFile, locate } from "../dist/index.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const fixture = path.join(__dirname, "fixtures", "parity.jsonl.gz");
const outDir = process.env.GRID_OUT || path.join(__dirname, "../../../artifacts/exact_out");

test("geohash encode length", () => {
  const g = encode(-1.95, 30.06, 9);
  assert.equal(g.length, 9);
});

test("parity with Python fixtures if present", async (t) => {
  if (!fs.existsSync(fixture)) {
    t.skip("no fixtures/parity.jsonl.gz yet");
    return;
  }
  if (!fs.existsSync(path.join(outDir, "root.bin.gz"))) {
    t.skip("no root.bin.gz");
    return;
  }
  const index = await loadRootFile(path.join(outDir, "root.bin.gz"));
  const lines = zlib.gunzipSync(fs.readFileSync(fixture)).toString("utf8").trim().split("\n");
  let disagree = 0;
  const t0 = performance.now();
  for (const line of lines) {
    const o = JSON.parse(line);
    const r = await locate(index, o.lat, o.lng, { outDir });
    if (r.village_code !== o.village || r.key !== o.key) disagree++;
  }
  const ms = performance.now() - t0;
  const p95approx = ms / lines.length;
  console.log(JSON.stringify({ n: lines.length, disagree, mean_ms: p95approx }));
  assert.equal(disagree, 0);
  assert.ok(p95approx < 5, "mean lookup should be <5ms after load");
});
