// Тести чистих функцій js/map-nodes.js (node:test).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { normalizeMap } from "../../../education/static/education/js/api.js";
import { layoutGrade } from "../../../education/static/education/js/map-layout.js";
import {
  starsText, nodeLabel, classPctLabel, playUrl, canPlay, lessonHash, findByHash, findParaByHash,
  initialIndex, fogRegions, newlyRevealed, loadSeenFog, saveSeenFog, markJustFinished,
  consumeJustFinished, walkSteps,
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

test("nodeLabel: з class_pct (режим вчителя, фаза 20, FE-0645) додає частку класу", () => {
  assert.equal(
    nodeLabel({ kind: "item", number: 4, title: "Площина. Пряма. Промінь", state: "current", stars: 1, classPct: 51 }),
    "Урок 4. Площина. Пряма. Промінь — ти тут, 1 зірка з 3, у класі 51% зі зіркою");
  assert.equal(nodeLabel({ kind: "item", number: 5, title: "Шкала", state: "locked", stars: 0, classPct: null }),
    "Урок 5. Шкала — закрито");
});

test("classPctLabel — округлення", () => {
  assert.equal(classPctLabel(51), "51%");
  assert.equal(classPctLabel(50.6), "51%");
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

test("findParaByHash: параграф без конкретного уроку (телефон, фаза 11, FE-0448)", () => {
  const m = load("grade-5.json");
  assert.equal(findParaByHash(m, "#para-49"), 3);    // §1 — current, урок 4
  assert.equal(findParaByHash(m, "#para-50"), 6);    // §2 — усе «у хмарах», перший урок параграфа
  assert.equal(findParaByHash(m, "#para-999"), -1);  // немає такого параграфа
  assert.equal(findParaByHash(m, "#lesson-117"), -1); // інший формат хеша
});

test("fogRegions: у реальному стані хмари над §2–§5, найбільша — §5 або §3", () => {
  const m = load("grade-5.json"), { fog, biggest } = fogRegions(m, layoutGrade(m));
  assert.deepEqual(fog.map((r) => r.paraIdx + 1), [2, 3, 4, 5]);
  assert.ok([3, 5].includes(biggest.paraIdx + 1));
  const demo = load("grade-5.demo.json");
  assert.equal(fogRegions(demo, layoutGrade(demo)).fog.length, 0);
});

test("newlyRevealed: лише ті, що вийшли з хмари; перший візит нічого не показує", () => {
  assert.deepEqual(newlyRevealed(null, [1, 2]), []);                    // перший візит — немає з чим звіряти
  assert.deepEqual(newlyRevealed([], [1, 2]), []);
  assert.deepEqual(newlyRevealed([1, 2, 3], [2]), [1, 3]);              // 1 і 3 вийшли з хмари
  assert.deepEqual(newlyRevealed([1, 2], [1, 2]), []);                  // нічого не змінилось
  assert.deepEqual(newlyRevealed([1, 2], [1, 2, 3]), []);               // новий параграф у хмарі — не «вихід»
});

test("loadSeenFog/saveSeenFog: без localStorage (Node) — тихо null, без винятків", () => {
  assert.equal(loadSeenFog(5), null);
  assert.doesNotThrow(() => saveSeenFog(5, [1, 2]));
});

test("loadSeenFog/saveSeenFog: округлення по класах, переживає биті дані", () => {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
  };
  try {
    assert.equal(loadSeenFog(5), null);
    saveSeenFog(5, [10, 11]);
    assert.deepEqual(loadSeenFog(5), [10, 11]);
    assert.equal(loadSeenFog(6), null);                  // інший клас — окремий ключ
    store.set("mw_fog_seen_grade_7", "не json{");
    assert.equal(loadSeenFog(7), null);                   // биті дані — не падає
  } finally {
    delete globalThis.localStorage;
  }
});

test("markJustFinished/consumeJustFinished: без sessionStorage (Node) — тихо null", () => {
  assert.equal(consumeJustFinished(5), null);
  assert.doesNotThrow(() => markJustFinished(5, "#lesson-120"));
});

test("markJustFinished/consumeJustFinished: одноразовий прапорець, клас має збігтись", () => {
  const store = new Map();
  globalThis.sessionStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
    removeItem: (k) => store.delete(k),
  };
  try {
    markJustFinished(5, "#lesson-120");
    assert.equal(consumeJustFinished(6), null);            // інший клас — не той прапорець
    assert.equal(store.size, 0);                            // consumeJustFinished прибрав його й для чужого класу
    markJustFinished(5, "#lesson-120");
    assert.equal(consumeJustFinished(5), "#lesson-120");
    assert.equal(consumeJustFinished(5), null);             // другий раз — уже нема
  } finally {
    delete globalThis.sessionStorage;
  }
});

test("walkSteps: від і до, пропускає «у хмарах» проміжні, обмежує задовгі переходи", () => {
  const L = (states) => states.map((state) => ({ state }));
  assert.deepEqual(walkSteps(L(["done", "current"]), 0, 1), [0, 1]);
  assert.deepEqual(walkSteps(L(["done", "soon", "soon", "current"]), 0, 3), [0, 3]);   // пропущені хмари
  assert.deepEqual(walkSteps(L(["done", "open", "current"]), 0, 2), [0, 1, 2]);        // проміжний не в хмарі — лишається
  assert.deepEqual(walkSteps(L(["current", "done"]), 1, 0), [1, 0]);                   // напрямок назад
  const long = L(Array.from({ length: 10 }, () => "open"));
  assert.deepEqual(walkSteps(long, 0, 9), [0, 9]);                                     // забагато кроків — лише кінці
});

test("tagSide: ярлик «Ти тут» не закриває сусідні вузли (фаза 17)", async () => {
  const { tagSide } = await import("../../../education/static/education/js/map-nodes.js");
  const me = { x: 100, y: 200 };
  assert.equal(tagSide(me, [me]), "above");
  assert.equal(tagSide(me, [me, { x: 100, y: 120 }]), "below");                       // вузол над ним
  assert.equal(tagSide(me, [me, { x: 100, y: 120 }, { x: 100, y: 285 }]), "right");   // і під ним
  assert.equal(tagSide(me, [me, { x: 100, y: 120 }, { x: 100, y: 285 }, { x: 180, y: 200 }]), "left");
});
