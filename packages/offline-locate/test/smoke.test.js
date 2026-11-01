import { test } from "node:test";
import assert from "node:assert/strict";
import { TAU } from "../dist/index.js";

test("TAU default", () => {
  assert.equal(TAU, 0.8);
});
