import { test } from "node:test";
import assert from "node:assert/strict";
import { nearby } from "../dist/index.js";

test("nearby empty without tiles", async () => {
  const r = await nearby(-1.95, 30.06, { radius_m: 500 });
  assert.equal(r.length, 0);
});
