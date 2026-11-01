import { test } from "node:test";
import assert from "node:assert/strict";
import { buildStyle } from "../dist/index.js";

test("relative paths only", () => {
  const s = buildStyle({ baseUrl: ".." });
  const text = JSON.stringify(s);
  assert.equal(/https?:\/\//.test(text), false);
  assert.ok(text.includes("pmtiles://"));
});
