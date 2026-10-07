// Юніт-тести JS-помічників (node:test, без залежностей). Запуск: npm test у tools/frontend.
import { test } from "node:test";
import assert from "node:assert/strict";
import { plural, count } from "../../../education/static/education/js/ui.js";

const DAYS = ["день", "дні", "днів"];

test("plural: 1, 21, 101 → день", () => {
  for (const n of [1, 21, 31, 101]) assert.equal(plural(n, DAYS), "день", String(n));
});

test("plural: 2–4, 22–24 → дні", () => {
  for (const n of [2, 3, 4, 22, 23, 24, 102]) assert.equal(plural(n, DAYS), "дні", String(n));
});

test("plural: 0, 5–20, 25 → днів", () => {
  for (const n of [0, 5, 9, 10, 11, 12, 13, 14, 15, 19, 20, 25, 111, 112]) {
    assert.equal(plural(n, DAYS), "днів", String(n));
  }
});

test("plural: дивні входи не ламаються", () => {
  assert.equal(plural("4", DAYS), "дні");
  assert.equal(plural(undefined, DAYS), "днів");
  assert.equal(plural(-1, DAYS), "день");
});

test("count", () => {
  assert.equal(count(38, ["урок", "уроки", "уроків"]), "38 уроків");
  assert.equal(count(4, DAYS), "4 дні");
});
