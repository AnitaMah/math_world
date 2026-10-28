// Мова уроків (фаза 20, беклог FE-0642): українська чи німецька. На відміну від теми (FE-0636),
// це cookie, не localStorage — шаблони уроку/параграфа й /api/grades/<n>/map/ рендеряться на
// сервері й мають читати вибір на кожен запит, тож зміна мови перезавантажує сторінку.
const COOKIE = "mw_lang";
const VALID = new Set(["uk", "de"]);

function readCookie(name) {
  const m = globalThis.document?.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

/** Поточний вибір: "uk" | "de" (за замовчуванням "uk" — немає cookie або значення биті). */
export function getLang() {
  const v = readCookie(COOKIE);
  return VALID.has(v) ? v : "uk";
}

function setLang(lang) {
  if (!VALID.has(lang)) return;
  document.cookie = `${COOKIE}=${lang}; path=/; max-age=31536000; samesite=lax`;
  globalThis.location?.reload();
}

/** Підключає кнопки [data-lang-pick] ("uk"/"de"), підсвічує активну. */
export function mountLangPicker(root) {
  const sync = () => {
    const current = getLang();
    for (const btn of root.querySelectorAll("[data-lang-pick]")) {
      btn.setAttribute("aria-pressed", String(btn.dataset.langPick === current));
    }
  };
  root.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-lang-pick]");
    if (!btn || btn.dataset.langPick === getLang()) return;
    setLang(btn.dataset.langPick);
  });
  sync();
}
