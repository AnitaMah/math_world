// Тести js/api.js на моках (node:test). Запуск: npm test у tools/frontend.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { deriveState, deriveTasks, normalizeMap, roman, stripNumber, mockMode } from "../../../education/static/education/js/api.js";

const mock = (name) => JSON.parse(readFileSync(new URL(`../../../education/static/education/mock/${name}`, import.meta.url), "utf8"));

test("deriveState: 5 випадків", () => {
  const cur = { kind: "item", id: 4 };
  assert.equal(deriveState({ id: 1, total: 0 }, cur), "soon");
  assert.equal(deriveState({ id: 1, total: 18, stars: 2 }, cur), "done");
  assert.equal(deriveState({ id: 4, total: 17, stars: 1, kind: "item" }, cur), "current");
  assert.equal(deriveState({ id: 5, total: 12, stars: 0 }, cur), "open");
  assert.equal(deriveState({ id: 5, total: 12, state: "locked" }, cur), "locked");  // з бекенду — як є
});

test("deriveState: старий API без total, лише exercises", () => {
  assert.equal(deriveState({ id: 9, exercises: 0 }, null), "soon");
  assert.equal(deriveState({ id: 9, exercises: 22, stars: 0 }, null), "open");
});

test("deriveTasks з tasks і без", () => {
  assert.deepEqual(deriveTasks({ tasks: { auto: 15, ai: 3 } }), { auto: 15, ai: 3, approx: false });
  assert.deepEqual(deriveTasks({ exercises: 22 }), { auto: 22, ai: 0, approx: true });
  assert.deepEqual(deriveTasks({}), { auto: 0, ai: 0, approx: true });
});

test("roman і stripNumber", () => {
  assert.deepEqual([1, 2, 3, 4, 5, 10].map(roman), ["I", "II", "III", "IV", "V", "X"]);
  assert.equal(roman(11), "11");
  assert.equal(stripNumber("§ 1. Натуральні числа"), "Натуральні числа");
  assert.equal(stripNumber("Розділ II. Дробові числа і дії з ними"), "Дробові числа і дії з ними");
  assert.equal(stripNumber("Розділ 3. Відношення і пропорції"), "Відношення і пропорції");
});

test("normalizeMap: 5 клас — 38 уроків, 5 параграфів, 2 розділи", () => {
  const m = normalizeMap(mock("grade-5.json"));
  assert.equal(m.lessons.length, 38);
  assert.equal(m.paragraphs.length, 5);
  assert.equal(m.sections.length, 2);
  assert.deepEqual(m.sections.map((s) => s.roman), ["I", "II"]);
  assert.deepEqual(m.paragraphs.map((p) => p.isl), [1, 2, 3, 4, 5]);
  const states = m.lessons.slice(0, 7).map((l) => l.state);
  assert.deepEqual(states, ["done", "done", "done", "current", "locked", "locked", "soon"]);
  assert.equal(m.lessons[0].kind, "item");
  assert.equal(m.lessons[0].tasks.auto, 15);
  assert.equal(m.lessons[6].paraIdx, 1);   // урок 7 — у §2
  assert.equal(m.lessons[0].classPct, 51);        // режим вчителя (фаза 20, беклог FE-0645)
  assert.equal(m.lessons[6].classPct, null);       // «у хмарах» — немає з чого рахувати
});

test("normalizeMap: 6 клас — 35 уроків kind: paragraph, кольори островів по колу", () => {
  const m = normalizeMap(mock("grade-6.json"));
  assert.equal(m.lessons.length, 35);
  assert.ok(m.lessons.every((l) => l.kind === "paragraph" && l.state === "soon"));
  assert.equal(m.sections.length, 5);
  assert.equal(m.paragraphs[5].isl, 1);   // §6 — знову бірюзовий
});

test("normalizeMap: демо — 9 пройдених уроків, поточний 10-й", () => {
  const m = normalizeMap(mock("grade-5.demo.json"));
  assert.equal(m.lessons.filter((l) => l.state === "done").length, 9);
  assert.equal(m.lessons.find((l) => l.state === "current").number, 10);
});

test("mockMode з URL", () => {
  assert.equal(mockMode("?mock=1"), "1");
  assert.equal(mockMode("?mock=demo"), "demo");
  assert.equal(mockMode("?mock"), "1");
  assert.equal(mockMode("?mock=0"), "");
  assert.equal(mockMode(""), "");   // у node немає localStorage — тихо ""
});

test("mockMode: поза DEBUG моки вимкнені (фаза 17)", () => {
  assert.equal(mockMode("?mock=1", false), "");
  assert.equal(mockMode("?mock=demo", true), "demo");
});
