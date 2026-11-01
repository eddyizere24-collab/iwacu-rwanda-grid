import { test } from "node:test";
import assert from "node:assert/strict";
import { encode } from "../dist/geohash.js";
test("encode length", () => { assert.equal(encode(-1.95, 30.06, 9).length, 9); });
