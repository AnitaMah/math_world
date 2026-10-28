// Тема (фаза 20, беклог FE-0636, за запитом вчителів): темна, світла або системна.
// Застосування без блимання — у <head> base.html (інлайн-копія цієї ж логіки, модуль
// туди не встигає завантажитись до першого малювання). Тут — лише перемикач на «Профілі».
const KEY = "mw_theme";
const VALID = new Set(["light", "dark"]);

/** Збережений вибір: "light" | "dark" | null (системна, вибору не було). */
export function getStoredTheme() {
  try {
    const v = globalThis.localStorage?.getItem(KEY);
    return VALID.has(v) ? v : null;
  } catch {
    return null;   // приватне вікно, заблоковане сховище
  }
}

function applyTheme(theme) {
  const html = globalThis.document?.documentElement;
  if (!html) return;
  if (VALID.has(theme)) html.dataset.theme = theme;
  else delete html.dataset.theme;
}

/** Застосовує й запам'ятовує вибір. `null`/"system" — повернутись до системної теми. */
export function setTheme(theme) {
  const normalized = VALID.has(theme) ? theme : null;
  applyTheme(normalized);
  try {
    if (normalized) globalThis.localStorage?.setItem(KEY, normalized);
    else globalThis.localStorage?.removeItem(KEY);
  } catch {
    /* приватне вікно — тема діє лише в цій вкладці, без пам'яті між візитами */
  }
}

/** Підключає кнопки `[data-theme-pick]` (значення "light"/"dark"/"system") і підсвічує активну. */
export function mountThemePicker(root) {
  const sync = () => {
    const current = getStoredTheme() ?? "system";
    for (const btn of root.querySelectorAll("[data-theme-pick]")) {
      btn.setAttribute("aria-pressed", String(btn.dataset.themePick === current));
    }
  };
  root.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-theme-pick]");
    if (!btn) return;
    setTheme(btn.dataset.themePick === "system" ? null : btn.dataset.themePick);
    sync();
  });
  sync();
}
