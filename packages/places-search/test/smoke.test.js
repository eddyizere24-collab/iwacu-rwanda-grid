import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeName, buildIndex, search } from "../dist/index.js";

test("normalize apostrophes", () => {
  assert.equal(normalizeName("Kinyinya"), "kinyinya");
  assert.equal(normalizeName("Nyarugenge"), "nyarugenge");
});

test("exact rank 1", () => {
  const idx = buildIndex([
    { code: "1", level: "village", name: "Kinyinya", path: "Kigali / Gasabo / Kinyinya" },
    { code: "2", level: "district", name: "Gasabo", path: "Kigali / Gasabo" },
  ]);
  const r = search(idx, "Kinyinya", 5);
  assert.equal(r[0].code, "1");
});
