import test from "node:test";
import assert from "node:assert/strict";
// @ts-expect-error Node's type stripping requires the .ts extension.
import { formatNumber } from "./formatNumber.ts";

test("id memakai titik ribuan dan koma desimal", () => {
  assert.equal(formatNumber(667443, "id"), "667.443");
  assert.equal(formatNumber(24.645, "id", 3), "24,645");
});

test("en memakai koma ribuan dan titik desimal", () => {
  assert.equal(formatNumber(667443, "en"), "667,443");
  assert.equal(formatNumber(24.645, "en", 3), "24.645");
});

test("jumlah desimal tetap, dibulatkan wajar", () => {
  assert.equal(formatNumber(0.9128, "id", 3), "0,913");
  assert.equal(formatNumber(14, "id", 2), "14,00");
});

test("kosong atau bukan angka menjadi strip", () => {
  assert.equal(formatNumber(null, "id"), "-");
  assert.equal(formatNumber(undefined, "en", 2), "-");
  assert.equal(formatNumber(Number.NaN, "id"), "-");
  assert.equal(formatNumber(Number.POSITIVE_INFINITY, "id"), "-");
});
