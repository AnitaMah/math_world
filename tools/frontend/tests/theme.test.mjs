// Тести js/theme.js (node:test): темна/світла/системна тема (фаза 20, FE-0636).
import { test } from "node:test";
import assert from "node:assert/strict";
import { getStoredTheme, setTheme } from "../../../education/static/education/js/theme.js";

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

test("getStoredTheme: без localStorage (Node) — тихо null", () => {
  assert.equal(getStoredTheme(), null);
  assert.doesNotThrow(() => setTheme("dark"));
});

test("getStoredTheme: биті/чужі значення не визнаються темою", () => {
  withFakeDom(({ store }) => {
    store.set("mw_theme", "sepia");
    assert.equal(getStoredTheme(), null);
  });
});

test("setTheme: явний вибір ставить data-theme і запам'ятовує", () => {
  withFakeDom(({ dataset }) => {
    setTheme("light");
    assert.equal(dataset.theme, "light");
    assert.equal(getStoredTheme(), "light");
    setTheme("dark");
    assert.equal(dataset.theme, "dark");
    assert.equal(getStoredTheme(), "dark");
  });
});

test("setTheme: null/\"system\" прибирає data-theme і забуває вибір", () => {
  withFakeDom(({ dataset }) => {
    setTheme("light");
    setTheme(null);
    assert.equal("theme" in dataset, false);
    assert.equal(getStoredTheme(), null);
    setTheme("dark");
    setTheme("system");                 // будь-яке невалідне значення — теж системна
    assert.equal("theme" in dataset, false);
    assert.equal(getStoredTheme(), null);
  });
});
