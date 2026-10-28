// Режим вчителя (фаза 20, беклог FE-0645): перемикач у топбарі (видно лише вчителю —
// me.js виставляє `is_teacher`) показує/ховає `.node__pct` — % учнів класу зі зіркою на
// кожному вузлі мапи (map-nodes.js, map.css). Дані — `class_pct` на `GET /api/grades/<n>/map/
// ?class_id=<id>` (контракт зафіксований FE-0640, docs/frontend/DECISIONS.md, 2026-10-28);
// клас обирає teacher-classes.js. Подія `teacher-mode:change` — map.js перезавантажує мапу
// (з/без `class_id`, залежно від нового стану).
const KEY = "mw_teacher_mode";

/** Вимкнено за замовчуванням, поки вчитель не увімкнув явно. */
export function isTeacherModeOn() {
  try {
    return globalThis.localStorage?.getItem(KEY) === "1";
  } catch {
    return false;   // приватне вікно, заблоковане сховище
  }
}

function applyTeacherMode(on) {
  const html = globalThis.document?.documentElement;
  if (!html) return;
  if (on) html.dataset.teacherMode = "1";
  else delete html.dataset.teacherMode;
}

export function setTeacherModeOn(on) {
  applyTeacherMode(on);
  try {
    if (on) globalThis.localStorage?.setItem(KEY, "1");
    else globalThis.localStorage?.removeItem(KEY);
  } catch {
    /* приватне вікно — перемикач діє лише в цій вкладці */
  }
  globalThis.document?.dispatchEvent(new CustomEvent("teacher-mode:change"));
}

/** Підключає кнопку-перемикач у топбарі; саму кнопку показує/ховає me.js (`is_teacher`). */
export function mountTeacherModeToggle(btn) {
  const sync = () => {
    const on = isTeacherModeOn();
    btn.setAttribute("aria-pressed", String(on));
    btn.setAttribute("aria-label", on ? "Режим вчителя увімкнено, вимкнути" : "Режим вчителя вимкнено, увімкнути");
  };
  btn.addEventListener("click", () => {
    setTeacherModeOn(!isTeacherModeOn());
    sync();
  });
  applyTeacherMode(isTeacherModeOn());   // застосувати збережений вибір одразу, незалежно від ролі з /api/me/
  sync();
}
