// Тести чистих функцій телефонної мапи (js/map-mobile.js, layoutLessons).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { normalizeMap } from "../../../education/static/education/js/api.js";
import { layoutLessons } from "../../../education/static/education/js/map-layout.js";
import { groupsOf, groupOfLesson, groupMeta, swipeDirection, swipeDown } from "../../../education/static/education/js/map-mobile.js";

const load = (name) => normalizeMap(JSON.parse(readFileSync(
  new URL(`../../../education/static/education/mock/${name}`, import.meta.url), "utf8")));

test("групи: 5 клас — 5 параграфів, 6 клас — 5 розділів", () => {
  const g5 = groupsOf(load("grade-5.json")), g6 = groupsOf(load("grade-6.json"));
  assert.deepEqual(g5.map((g) => g.badge), ["§1", "§2", "§3", "§4", "§5"]);
  assert.deepEqual(g6.map((g) => g.badge), ["I", "II", "III", "IV", "V"]);
  assert.equal(g6[2].lessons.length, 9);
  assert.equal(groupOfLesson(g5, 3), 0);
  assert.equal(groupOfLesson(g5, 37), 4);
});

test("підзаголовок картки", () => {
  const map = load("grade-5.json"), g = groupsOf(map);
  assert.equal(groupMeta(map, g[0]), "Розділ I · 3 з 6 уроків · 8 / 18 ★");
  assert.equal(groupMeta(map, g[1]), "Розділ I · 0 з 9 уроків · ще в хмарах");
  const m6 = load("grade-6.json");
  assert.equal(groupMeta(m6, groupsOf(m6)[0]), "5 параграфів · ще в хмарах");
});

test("свайп: лише впевнений горизонтальний рух", () => {
  assert.equal(swipeDirection(-80, 10), 1);
  assert.equal(swipeDirection(90, -20), -1);
  assert.equal(swipeDirection(40, 0), 0);      // закоротко
  assert.equal(swipeDirection(-80, 70), 0);    // це прокрутка, а не свайп
});

test("swipeDown: згортання нижнього листа (фаза 11, беклог FE-0455)", () => {
  assert.equal(swipeDown(10, 80), true);
  assert.equal(swipeDown(0, -80), false);      // вгору — не згортання
  assert.equal(swipeDown(10, 40), false);      // закоротко
  assert.equal(swipeDown(70, 80), false);      // це горизонтальний свайп, не вертикальний
});

test("layoutLessons: 9 уроків розділу III 6 класу — вертикально, крок 76", () => {
  const map = load("grade-6.json"), g = groupsOf(map)[2];
  const L = layoutLessons(map, g.lessons, { isl: g.isl, key: 2 });
  assert.equal(L.nodes.length, 9);
  assert.equal(L.nodes[8].y - L.nodes[0].y, 8 * 76);
  assert.equal(L.height, L.nodes[8].y + 220);
  assert.ok(L.nodes.every((n) => n.x >= 80 && n.x <= 310));
});
