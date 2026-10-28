// Тести js/teacher-mode.js (node:test): перемикач «Режим вчителя» (фаза 20, беклог FE-0645).
import { test } from "node:test";
import assert from "node:assert/strict";
import { isTeacherModeOn, setTeacherModeOn } from "../../../education/static/education/js/teacher-mode.js";

function withFakeDom(fn) {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
    removeItem: (k) => store.delete(k),
  };
  const dataset = {};
  globalThis.document = { documentElement: { dataset } };
  try {
    fn({ store, dataset });
  } finally {
    delete globalThis.localStorage;
    delete globalThis.document;
  }
}

test("isTeacherModeOn: без localStorage (Node) — тихо false (вимкнено за замовчуванням)", () => {
  assert.equal(isTeacherModeOn(), false);
  assert.doesNotThrow(() => setTeacherModeOn(true));
});

test("isTeacherModeOn/setTeacherModeOn: увімкнення і вимкнення запам'ятовується, пише data-teacher-mode", () => {
  withFakeDom(({ store, dataset }) => {
    assert.equal(isTeacherModeOn(), false);
    setTeacherModeOn(true);
    assert.equal(store.get("mw_teacher_mode"), "1");
    assert.equal(isTeacherModeOn(), true);
    assert.equal(dataset.teacherMode, "1");
    setTeacherModeOn(false);
    assert.equal(store.has("mw_teacher_mode"), false);
    assert.equal(isTeacherModeOn(), false);
    assert.equal("teacherMode" in dataset, false);
  });
});
