// Тести js/sound.js (node:test): вимикач звуку правильної/неправильної відповіді (фаза 20, FE-0637).
import { test } from "node:test";
import assert from "node:assert/strict";
import { isSoundOn, setSoundOn, playFeedbackSound } from "../../../education/static/education/js/sound.js";

function withFakeStorage(fn) {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
  };
  try {
    fn(store);
  } finally {
    delete globalThis.localStorage;
  }
}

test("isSoundOn: без localStorage (Node) — тихо true (звук за замовчуванням увімкнено)", () => {
  assert.equal(isSoundOn(), true);
  assert.doesNotThrow(() => setSoundOn(false));
});

test("isSoundOn/setSoundOn: вмикання і вимикання запам'ятовується", () => {
  withFakeStorage((store) => {
    assert.equal(isSoundOn(), true);          // нічого не збережено — увімкнено
    setSoundOn(false);
    assert.equal(store.get("mw_sound"), "0");
    assert.equal(isSoundOn(), false);
    setSoundOn(true);
    assert.equal(store.get("mw_sound"), "1");
    assert.equal(isSoundOn(), true);
  });
});

test("playFeedbackSound: без AudioContext (Node) і без звуку (вимкнено) — не падає", () => {
  assert.doesNotThrow(() => playFeedbackSound("ok"));
  assert.doesNotThrow(() => playFeedbackSound("bad"));
  withFakeStorage(() => {
    setSoundOn(false);
    assert.doesNotThrow(() => playFeedbackSound("ok"));
  });
});
