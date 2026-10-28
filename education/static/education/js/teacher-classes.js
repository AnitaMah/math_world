// Клас, яким керує вчитель (фаза 20, беклог FE-0645): перемикач «Режим вчителя» (teacher-mode.js)
// не знає, ЯКИЙ клас показувати — якщо вчитель керує більш ніж одним, топбар дає вибір
// (`#teacherClassPicker`). Вибір пам'ятається в localStorage, map.js читає його синхронно
// (currentClassId) перед запитом мапи — без зайвого походу на /api/classes/mine/ при кожному
// завантаженні.
import { api } from "./api.js";
import { isTeacherModeOn } from "./teacher-mode.js";

const KEY = "mw_teacher_class";

function getStoredClassId() {
  try {
    const v = Number(globalThis.localStorage?.getItem(KEY));
    return Number.isInteger(v) && v > 0 ? v : null;
  } catch {
    return null;   // приватне вікно, заблоковане сховище
  }
}

function setStoredClassId(id) {
  try {
    if (id) globalThis.localStorage?.setItem(KEY, String(id));
    else globalThis.localStorage?.removeItem(KEY);
  } catch {
    /* приватне вікно — вибір діє лише в цій вкладці */
  }
}

/** Запам'ятаний клас, якщо він є серед доступних, інакше перший — чи `null`, якщо класів нема. */
export function pickDefaultClassId(classes, stored) {
  if (stored != null && classes.some((c) => c.id === stored)) return stored;
  return classes[0]?.id ?? null;
}

/** Клас для запиту мапи: лише коли режим вчителя увімкнено — інакше `class_id` не шлють зовсім. */
export function currentClassId() {
  return isTeacherModeOn() ? getStoredClassId() : null;
}

/**
 * Підключає `<select>` у топбарі: порожній список — ховає й себе, один клас — обирає його мовчки
 * (без видимого списку), два і більше — показує список з назвами шкіл/класів. onChange() кличуть
 * і при зміні вибору, і якщо запам'ятований клас довелось виправити (зник чи немає жодного) —
 * бо map.js уже встиг прочитати старий `currentClassId()` синхронно, до того як цей фетч завершився.
 */
export async function mountClassPicker(select, { onChange } = {}) {
  const before = getStoredClassId();
  const { ok, data } = await api.classes();
  const classes = ok ? data.classes ?? [] : [];
  const chosen = classes.length ? pickDefaultClassId(classes, before) : null;
  setStoredClassId(chosen);
  if (chosen !== before && isTeacherModeOn()) onChange?.();

  select.hidden = classes.length < 2;
  if (classes.length < 2) return;   // 0 — нема що обирати; 1 — обрано мовчки, без видимого списку
  select.replaceChildren(...classes.map((c) => {
    const opt = document.createElement("option");
    opt.value = String(c.id);
    opt.textContent = `${c.school_name} · ${c.name}`;
    return opt;
  }));
  select.value = String(chosen);
  select.addEventListener("change", () => {
    setStoredClassId(Number(select.value));
    onChange?.();
  });
}
