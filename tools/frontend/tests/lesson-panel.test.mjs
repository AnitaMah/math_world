// Тести моделі панелі уроку (js/lesson-panel.js), без DOM.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { normalizeMap } from "../../../education/static/education/js/api.js";
import { panelModel, islandRows, blockingLesson, theoryUrl } from "../../../education/static/education/js/lesson-panel.js";

const load = (name) => normalizeMap(JSON.parse(readFileSync(
  new URL(`../../../education/static/education/mock/${name}`, import.meta.url), "utf8")));

test("поточний урок 4 (реальний стан): заголовок, статус, кнопка «Продовжити», завдання", () => {
  const m = panelModel(load("grade-5.json"), 3);
  assert.equal(m.title, "Площина. Пряма. Промінь");
  assert.equal(m.section, "Розділ I · §1 Натуральні числа");
  assert.equal(m.status, "Ти тут");
  assert.equal(m.position, "Урок 4 з 38");
  assert.deepEqual(m.cta, { text: "Продовжити", href: "/play/item/120/", style: "primary" });
  assert.equal(m.solvedText, "Розв’язано 4 з 17");
  assert.equal(m.autoText, "14 вправ з автоперевіркою");
  assert.equal(m.aiText, "3 текстові задачі з ШІ");
  assert.ok(m.blocks.includes("Задача Мудрої Сови") && m.blocks.includes("Коли зроблено уроки"));
  assert.equal(m.theoryHref, "/items/120/");
  assert.equal(m.isl, 1);
});

test("кнопка за станом: пройдено / закрито / у хмарах", () => {
  const map = load("grade-5.json");
  assert.equal(panelModel(map, 0).cta.text, "Пройти ще раз");
  assert.equal(panelModel(map, 0).cta.style, "info");
  const locked = panelModel(map, 4);
  assert.deepEqual(locked.cta, { text: "Спершу пройди урок 4", href: null, style: "muted" });
  const soon = panelModel(map, 10);
  assert.equal(soon.cta.text, "Скоро");
  assert.equal(soon.hasTasks, false);
  assert.equal(soon.solvedText, "Завдань поки немає");
  assert.equal(soon.theoryHref, "/items/127/");   // теорію читати можна завжди
});

test("відмінювання і «приблизно» для старого API", () => {
  const map = load("grade-5.json");
  map.lessons[0].tasks = { auto: 1, ai: 1, approx: false };
  assert.equal(panelModel(map, 0).autoText, "1 вправа з автоперевіркою");
  assert.equal(panelModel(map, 0).aiText, "1 текстова задача з ШІ");
  map.lessons[0].tasks = { auto: 22, ai: 0, approx: true };
  const m = panelModel(map, 0);
  assert.equal(m.autoText, "≈ 22 вправи з автоперевіркою");
  assert.equal(m.showAi, false);
});

test("blockingLesson пропускає уроки без завдань", () => {
  const map = load("grade-5.json");
  map.lessons[4].total = 0;   // урок 5 — «у хмарах»
  assert.equal(blockingLesson(map, 5).number, 4);
  assert.equal(blockingLesson(map, 0), null);
});

test("6 клас: урок = §, острови по розділах", () => {
  const map = load("grade-6.json");
  const m = panelModel(map, 0);
  assert.equal(m.position, "Параграф 1 з 35");
  assert.equal(m.title, "Дільники і кратні натурального числа");
  assert.equal(m.theoryHref, `/paragraphs/${map.lessons[0].id}/`);
  const rows = islandRows(map);
  assert.equal(rows.length, 5);
  assert.equal(rows[0].label, "Розділ I Подільність натуральних чисел");
  assert.equal(rows[0].score, "0 / 15 ★");
});

test("5 клас: острови по параграфах, рахунок зірок, куди веде рядок", () => {
  const rows = islandRows(load("grade-5.json"));
  assert.deepEqual(rows.map((r) => r.label), ["I · §1 Натуральні числа", "I · §2 Додавання і віднімання натуральних чисел",
    "I · §3 Множення і ділення натуральних чисел", "II · §4 Звичайні дроби", "II · §5 Десяткові дроби"]);
  assert.equal(rows[0].score, "8 / 18 ★");
  assert.equal(rows[0].target, 3);          // поточний урок 4
  const demo = islandRows(load("grade-5.demo.json"));
  assert.equal(demo[1].score, "8 / 27 ★");   // уроки 7–9: 2 + 3 + 3
});

test("theoryUrl", () => {
  assert.equal(theoryUrl({ kind: "item", id: 5 }), "/items/5/");
  assert.equal(theoryUrl({ kind: "paragraph", id: 54 }), "/paragraphs/54/");
});

test("lessonListModel: текстова альтернатива мапи (фаза 16)", async () => {
  const { lessonListModel } = await import("../../../education/static/education/js/lesson-panel.js");
  const map = {
    paragraphs: [{ number: 1, shortTitle: "Натуральні числа", lessonIdx: [0, 1] }],
    lessons: [
      { kind: "item", id: 7, number: 1, title: "Ряд чисел", state: "done", stars: 2 },
      { kind: "item", id: 8, number: 2, title: "Цифри", state: "soon", stars: 0 },
    ],
  };
  const [g] = lessonListModel(map);
  assert.equal(g.heading, "§1. Натуральні числа");
  assert.equal(g.lessons[0].href, "/items/7/");
  assert.match(g.lessons[0].text, /^Урок 1\. Ряд чисел — пройдено/);
  assert.equal(g.lessons[1].href, "");
});
