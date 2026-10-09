// Тести js/map-layout.js на моках (node:test). Запуск: npm test у tools/frontend.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { normalizeMap } from "../../../education/static/education/js/api.js";
import {
  mulberry32, blob, inside, layoutGrade, layoutParagraph, pickIcon, chipName,
} from "../../../education/static/education/js/map-layout.js";

const load = (name) => normalizeMap(JSON.parse(readFileSync(
  new URL(`../../../education/static/education/mock/${name}`, import.meta.url), "utf8")));
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const MOCKS = ["grade-5.json", "grade-5.demo.json", "grade-5.states.json", "grade-6.json"];

test("mulberry32: однаковий seed → однакова послідовність", () => {
  const a = mulberry32(5038), b = mulberry32(5038), c = mulberry32(5039);
  const sa = [...Array(5)].map(a), sb = [...Array(5)].map(b), sc = [...Array(5)].map(c);
  assert.deepEqual(sa, sb);
  assert.notDeepEqual(sa, sc);
  assert.ok(sa.every((x) => x >= 0 && x < 1));
});

test("blob: M … n×C … Z, цілі координати", () => {
  const { d } = blob(100, 100, 50, 30, mulberry32(1), 10, 0.1);
  assert.match(d, /^M-?\d+,-?\d+ /);
  assert.ok(d.endsWith("Z"));
  assert.equal((d.match(/C/g) || []).length, 10);
  assert.doesNotMatch(d, /\./);
});

test("5 клас: острів I ≈ 0–645, острів II ≈ 700–1050 (як у макеті)", () => {
  const L = layoutGrade(load("grade-5.json"));
  const [I, II] = L.islands.map((i) => i.rect);
  assert.ok(Math.abs(I.x - 0) <= 40 && Math.abs(I.x + I.w - 645) <= 40, JSON.stringify(I));
  assert.ok(Math.abs(II.x - 700) <= 40 && Math.abs(II.x + II.w - 1050) <= 40, JSON.stringify(II));
});

test("острови не перетинаються, між ними коридор ≥ 50 px", () => {
  for (const f of MOCKS) {
    const rects = layoutGrade(load(f)).islands.map((i) => i.rect);
    for (let i = 0; i < rects.length; i++) for (let j = i + 1; j < rects.length; j++) {
      const a = rects[i], b = rects[j];
      const gapX = Math.max(b.x - (a.x + a.w), a.x - (b.x + b.w));
      const gapY = Math.max(b.y - (a.y + a.h), a.y - (b.y + b.h));
      assert.ok(Math.max(gapX, gapY) >= 50, `${f}: острови ${i} і ${j} ближче 50 px`);
    }
  }
});

test("центр кожної ділянки й кожен вузол — усередині свого острова", () => {
  for (const f of MOCKS) {
    const m = load(f), L = layoutGrade(m);
    for (const r of L.regions) assert.ok(inside({ x: r.cx, y: r.cy }, L._polys[r.sectionIdx]), `${f}: §${r.paraIdx + 1}`);
    for (const n of L.nodes) {
      assert.ok(inside(n, L._polys[m.lessons[n.lessonIdx].sectionIdx]), `${f}: урок ${n.lessonIdx + 1}`);
    }
  }
});

test("усі вузли на відстані ≥ 56 px один від одного (5 і 6 клас)", () => {
  for (const f of MOCKS) {
    const L = layoutGrade(load(f));
    assert.equal(L.nodes.length, f.startsWith("grade-6") ? 35 : 38);
    for (let i = 0; i < L.nodes.length; i++) for (let j = i + 1; j < L.nodes.length; j++) {
      assert.ok(dist(L.nodes[i], L.nodes[j]) >= 56, `${f}: уроки ${i + 1} і ${j + 1}`);
    }
  }
});

test("вузли — в межах полотна", () => {
  for (const f of MOCKS) {
    const L = layoutGrade(load(f));
    for (const n of L.nodes) assert.ok(n.x >= 30 && n.x <= L.width - 30 && n.y >= 30 && n.y <= L.height - 30, `${f}: ${JSON.stringify(n)}`);
  }
});

test("конектори з’єднують сусідні уроки на межі параграфів; човен — між островами", () => {
  const m = load("grade-5.json"), L = layoutGrade(m);
  const pairs = L.connectors.map((c) => [c.from + 1, c.to + 1, c.kind]);
  assert.deepEqual(pairs, [[6, 7, "land"], [15, 16, "land"], [24, 25, "boat"], [29, 30, "land"]]);
  const boat = L.connectors.find((c) => c.kind === "boat");
  assert.ok(boat.boat && Number.isInteger(boat.boat.x));
});

test("ручні координати уроку мають пріоритет", () => {
  const m = load("grade-5.json");
  m.lessons[0].map = { x: 333, y: 444 };
  const L = layoutGrade(m);
  assert.deepEqual([L.nodes[0].x, L.nodes[0].y], [333, 444]);
});

test("чіпи: на параграф у 5 класі, на розділ у 6-му; не налазять один на одного", () => {
  const c5 = layoutGrade(load("grade-5.json")).chips, c6 = layoutGrade(load("grade-6.json")).chips;
  assert.equal(c5.length, 5);
  assert.deepEqual(c5.map((c) => c.badge), ["I · §1", "I · §2", "I · §3", "II · §4", "II · §5"]);
  assert.equal(c6.length, 5);
  assert.ok(c6.every((c) => c.badge.startsWith("Розділ ")));
  for (const chips of [c5, c6]) for (let i = 0; i < chips.length; i++) for (let j = i + 1; j < chips.length; j++) {
    const a = chips[i], b = chips[j];
    const overlap = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
    assert.ok(!overlap, `${a.text} / ${b.text}`);
  }
});

test("chipName: короткі назви", () => {
  assert.equal(chipName("Натуральні числа"), "Натуральні числа");
  assert.equal(chipName("Додавання і віднімання натуральних чисел"), "Додавання і віднімання");
  assert.equal(chipName("Перетворення звичайного дробу в десятковий"), "Перетворення звичайного дробу");
  assert.equal(chipName("Подільність натуральних чисел і ще"), "Подільність натуральних чисел");
});

test("pickIcon на 5 реальних параграфах 5 класу", () => {
  const m = load("grade-5.json");
  const icon = (p) => pickIcon(m.paragraphs[p].shortTitle, m.paragraphs[p].lessonIdx.map((i) => m.lessons[i].title));
  assert.deepEqual([0, 1, 2, 3, 4].map(icon), ["ruler", "triangle", "cube", "pie", "decimal"]);
  assert.equal(pickIcon("Відсотки"), "percent");
  assert.equal(pickIcon("Щось без ключових слів"), null);
});

test("телефон: §1 — 6 вузлів «змійкою» поруч із макетом Mobile (±35 px)", () => {
  const P = layoutParagraph(load("grade-5.json"), 0);
  const design = [[190, 200], [285, 270], [275, 355], [185, 425], [100, 500], [150, 580]];
  P.nodes.forEach((n, i) => {
    assert.ok(Math.abs(n.x - design[i][0]) <= 35 && Math.abs(n.y - design[i][1]) <= 35, `урок ${i + 1}: ${n.x},${n.y}`);
  });
  assert.equal(P.height, 580 + 220);
  assert.equal(P.isl, 1);
});

// Поріг — від катастрофічного уповільнення, не бенчмарк: на слабкому ноутбуці з Windows
// перший прогін (прогрів JIT) ішов 160 мс, тож міряємо медіану 5 прогонів після прогріву.
test("кеш і швидкість: 6 клас — медіана < 100 мс", () => {
  const m = load("grade-6.json");
  const a = layoutGrade(m);
  assert.equal(layoutGrade(m), a);           // той самий об’єкт із кешу
  layoutGrade(m, { seed: 1 });               // прогрів
  const times = [2, 3, 4, 5, 6].map((seed) => {
    const t = performance.now();
    layoutGrade(m, { seed });                // без кешу (інший seed)
    return performance.now() - t;
  }).sort((x, y) => x - y);
  assert.ok(times[2] < 100, `медіана ${times[2].toFixed(1)} мс`);
});
