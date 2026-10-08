// Тести картки класу на екрані «Світ» (js/world.js, без DOM).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { normalizeMap } from "../../../education/static/education/js/api.js";
import { gradeSummary } from "../../../education/static/education/js/world.js";

const load = (name) => normalizeMap(JSON.parse(readFileSync(
  new URL(`../../../education/static/education/mock/${name}`, import.meta.url), "utf8")));

test("5 клас (реальний стан): 8 зірок з 114, «Продовжити · урок 4»", () => {
  assert.deepEqual(gradeSummary(load("grade-5.json")), { building: false, stars: 8, max: 114, cta: "Продовжити · урок 4" });
});

test("новий гравець — «Почати з уроку 1»", () => {
  const m = load("grade-5.json");
  m.lessons.forEach((l) => { l.stars = 0; l.state = l.total ? "open" : "soon"; });
  assert.equal(gradeSummary(m).cta, "Почати з уроку 1");
});

test("6 клас — мапа будується", () => {
  const s = gradeSummary(load("grade-6.json"));
  assert.equal(s.building, true);
  assert.equal(s.max, 105);
});
