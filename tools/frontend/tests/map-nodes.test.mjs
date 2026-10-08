// Тести чистих функцій js/map-nodes.js (node:test).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { normalizeMap } from "../../../education/static/education/js/api.js";
import { layoutGrade } from "../../../education/static/education/js/map-layout.js";
import {
  starsText, nodeLabel, playUrl, canPlay, lessonHash, findByHash, initialIndex, fogRegions,
} from "../../../education/static/education/js/map-nodes.js";

const load = (name) => normalizeMap(JSON.parse(readFileSync(
  new URL(`../../../education/static/education/mock/${name}`, import.meta.url), "utf8")));

test("starsText — відмінювання", () => {
  assert.deepEqual([0, 1, 2, 3].map(starsText), ["0 зірок з 3", "1 зірка з 3", "2 зірки з 3", "3 зірки з 3"]);
});

test("nodeLabel для скрінрідера", () => {
  assert.equal(nodeLabel({ kind: "item", number: 4, title: "Площина. Пряма. Промінь", state: "current", stars: 1 }),
    "Урок 4. Площина. Пряма. Промінь — ти тут, 1 зірка з 3");
  assert.equal(nodeLabel({ kind: "item", number: 5, title: "Шкала", state: "locked", stars: 0 }), "Урок 5. Шкала — закрито");
  assert.equal(nodeLabel({ kind: "paragraph", number: 12, title: "§ 12. Відношення", state: "soon", stars: 0 }),
    "§12. Відношення — ще не імпортовано");
});

test("playUrl, canPlay, якорі", () => {
  assert.equal(playUrl({ kind: "item", id: 120 }), "/play/item/120/");
  assert.equal(playUrl({ kind: "paragraph", id: 54 }), "/play/paragraph/54/");
  assert.deepEqual(["done", "current", "open", "locked", "soon"].map((state) => canPlay({ state })), [true, true, true, false, false]);
  assert.equal(lessonHash({ kind: "item", id: 120 }), "#lesson-120");
  assert.equal(lessonHash({ kind: "paragraph", id: 54 }), "#lesson-p54");
});

test("findByHash / initialIndex", () => {
  const m = load("grade-5.json");
  assert.equal(findByHash(m.lessons, "#lesson-118"), 1);
  assert.equal(findByHash(m.lessons, "#lesson-p49"), -1);
  assert.equal(findByHash(m.lessons, "#щось"), -1);
  assert.equal(initialIndex(m.lessons, ""), 3);            // поточний — урок 4
  assert.equal(initialIndex(m.lessons, "#lesson-117"), 0);
  const g6 = load("grade-6.json");
  assert.equal(initialIndex(g6.lessons, ""), 0);           // усе «у хмарах» — перший
});

test("fogRegions: у реальному стані хмари над §2–§5, найбільша — §5 або §3", () => {
  const m = load("grade-5.json"), { fog, biggest } = fogRegions(m, layoutGrade(m));
  assert.deepEqual(fog.map((r) => r.paraIdx + 1), [2, 3, 4, 5]);
  assert.ok([3, 5].includes(biggest.paraIdx + 1));
  const demo = load("grade-5.demo.json");
  assert.equal(fogRegions(demo, layoutGrade(demo)).fog.length, 0);
});
