// Логіка екрана гри (фаза 14): education/static/education/js/play-core.js
import test from "node:test";
import assert from "node:assert/strict";
import { errorFeedback, feedbackFor, finishModel, orderTasks, progressPct, taskView } from "../../../education/static/education/js/play-core.js";

const auto = (solved, extra = {}) => ({ kind: "auto", points: 2, solved,
  exercise: { id: 1, number: "78", difficulty: "high", condition: "Обчисли:", condition_tail: "", figures: [{ url: "/m/a.png", number: "5" }, { url: null }] },
  sub: { id: 9, number: "2", text: "25 + 17;" }, ...extra });
const ai = { kind: "ai", points: 5, solved: false, exercise: { id: 2, number: "95", difficulty: "", condition: "Задача", figures: [] }, sub: null };

test("orderTasks: спершу нерозв’язані, порядок уроку зберігається", () => {
  assert.deepEqual(orderTasks([auto(true), auto(false), auto(true), auto(false)]), [1, 3, 0, 2]);
});

test("progressPct", () => {
  assert.equal(progressPct([]), 0);
  assert.equal(progressPct([auto(true), auto(false), auto(false)]), 33);
});

test("taskView: авто-завдання з підпунктом", () => {
  const v = taskView(auto(false));
  assert.equal(v.isAi, false);
  assert.deepEqual(v.diff, { code: "high", name: "Високий" });
  assert.deepEqual(v.question, { label: "Вправа 78, 2)", text: "25 + 17" });
  assert.deepEqual(v.figures, [{ url: "/m/a.png", label: "Рис. 5" }]);
  assert.equal(v.button, "Перевірити");
});

test("taskView: ШІ-завдання", () => {
  const v = taskView(ai);
  assert.equal(v.isAi, true);
  assert.equal(v.diff, null);
  assert.equal(v.question, null);
  assert.equal(v.button, "Перевірити з ШІ");
  assert.match(v.hint, /Ctrl\+Enter/);
});

test("feedbackFor: правильно / неправильно / незрозуміло", () => {
  const ok = feedbackFor({ correct: true, points: 2 }, () => 0);
  assert.deepEqual([ok.kind, ok.title, ok.points], ["ok", "Чудово!", 2]);
  assert.equal(feedbackFor({ correct: true, points: 0, already_solved: true }).text, "Це завдання вже було розв’язано.");
  assert.equal(feedbackFor({ correct: false }).title, "Ще не так");
  assert.equal(feedbackFor({ correct: false, verdict: "unclear", feedback: "Допиши відповідь" }).text, "Допиши відповідь");
});

test("errorFeedback: ШІ недоступний — пропуск, мережа — повтор", () => {
  const off = errorFeedback({ ok: false, status: 503, data: { error: "ai_unavailable" } });
  assert.equal(off.skip, true);
  assert.equal(off.title, "ШІ зараз відпочиває");
  const net = errorFeedback({ ok: false, status: 0, data: { error: "network" } });
  assert.equal(net.retry, true);
  assert.equal(net.title, "Немає зв’язку");
  assert.equal(errorFeedback({ ok: false, status: 429, data: { detail: "Не більше 10 спроб" } }).text, "Не більше 10 спроб");
});

test("finishModel: усе розв’язано, нова зірка, наступний урок на 3★", () => {
  const m = finishModel({ tasks: [auto(true), auto(true)], progress: { stars: 3 }, startStars: 2, sessionPoints: 23, nextUrl: "/play/item/5/" });
  assert.equal(m.title, "Урок пройдено!");
  assert.equal(m.starsLabel, "3 з 3 зірок");
  assert.equal(m.newStar, "Нова зірка!");
  assert.equal(m.pointsText, "+23 бали");
  assert.equal(m.retry, false);
  assert.equal(m.next, true);
});

test("finishModel: частково, без нових зірок, без наступного", () => {
  const m = finishModel({ tasks: [auto(true), auto(false)], progress: { stars: 1 }, startStars: 1, sessionPoints: 1 });
  assert.equal(m.title, "Гарна робота!");
  assert.equal(m.summary, "Розв’язано 1 з 2");
  assert.equal(m.pointsText, "+1 бал");
  assert.equal(m.newStar, "");
  assert.equal(m.retry, true);
  assert.equal(m.next, false);
  assert.equal(finishModel({ tasks: [auto(false)], progress: null }).title, "Не здавайся!");
  assert.equal(finishModel({ tasks: [auto(true)], progress: { stars: 3 }, startStars: 0 }).newStar, "Нові зірки!");
});
