import { test } from "node:test";
import assert from "node:assert/strict";
import { buildStyle, REQUIRED_SOURCE_LAYERS } from "../dist/index.js";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

test("style version 8 and layers reference required source-layers", () => {
  const style = buildStyle({ baseUrl: "https://example.invalid/basemap" });
  assert.equal(style.version, 8);
  const used = new Set();
  for (const layer of style.layers) {
    if (layer["source-layer"]) used.add(layer["source-layer"]);
  }
  for (const name of REQUIRED_SOURCE_LAYERS) {
    assert.ok(used.has(name), `missing layer ref ${name}`);
  }
  const src = style.sources.rwanda;
  assert.match(src.url, /^pmtiles:\/\/https:\/\/example\.invalid\/basemap\/rwanda\.pmtiles$/);
});

test("optional boundaries layer",
  () => {
    const style = buildStyle({
      baseUrl: "https://x.test",
      boundariesUrl: "https://x.test/villages.geojson",
    });
    assert.ok(style.sources.boundaries);
    assert.ok(style.layers.some((l) => l.id === "admin-boundaries"));
  }
);

test("pmtiles layer list file if present", async (t) => {
  const p = process.env.PMTILES_LAYERS_JSON;
  if (!p || !fs.existsSync(p)) {
    t.skip("no PMTILES_LAYERS_JSON");
    return;
  }
  const layers = JSON.parse(fs.readFileSync(p, "utf8"));
  const ids = new Set(layers.map((x) => x.id || x));
  for (const name of REQUIRED_SOURCE_LAYERS) {
    assert.ok(ids.has(name), `pmtiles missing ${name}`);
  }
});
