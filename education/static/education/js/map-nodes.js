// Вузли уроків на мапі (фаза 9): 5 станів, зірки, «Ти тут», хмари, вибір уроку.
// Вузол — HTML <button> поверх SVG (фокус, клавіатура, скрінрідер), розмір масштабується через --s.
import { plural } from "./ui.js";

const STATE_WORDS = {
  done: "пройдено", current: "ти тут", open: "відкрито", locked: "закрито", soon: "ще не імпортовано",
};

export function starsText(n) {
  return `${n} ${plural(n, ["зірка", "зірки", "зірок"])} з 3`;
}

/** «Урок 4. Площина. Пряма. Промінь — ти тут, 1 зірка з 3» — для скрінрідера. */
export function nodeLabel(lesson) {
  const head = lesson.kind === "paragraph" ? `§${lesson.number}` : `Урок ${lesson.number}`;
  const title = String(lesson.title ?? "").replace(/^§\s*\d+\.\s*/, "");
  const tail = lesson.state === "done" || lesson.state === "current" ? `, ${starsText(lesson.stars)}` : "";
  return `${head}. ${title} — ${STATE_WORDS[lesson.state] ?? lesson.state}${tail}`;
}

/** Куди веде гра уроку. */
export function playUrl(lesson) {
  return lesson.kind === "paragraph" ? `/play/paragraph/${lesson.id}/` : `/play/item/${lesson.id}/`;
}

export const canPlay = (lesson) => ["done", "current", "open"].includes(lesson.state);

/** Якір у URL: #lesson-117 (пункт) або #lesson-p54 (§ як урок). */
export function lessonHash(lesson) {
  return `#lesson-${lesson.kind === "paragraph" ? "p" : ""}${lesson.id}`;
}

export function findByHash(lessons, hash) {
  const m = /^#lesson-(p?)(\d+)$/.exec(hash ?? "");
  if (!m) return -1;
  const kind = m[1] ? "paragraph" : "item", id = Number(m[2]);
  return lessons.findIndex((l) => l.kind === kind && l.id === id);
}

/** Який урок вибрати при відкритті: з URL → поточний → перший відкритий → перший. */
export function initialIndex(lessons, hash) {
  const fromHash = findByHash(lessons, hash);
  if (fromHash >= 0) return fromHash;
  const order = ["current", "open", "done"];
  for (const st of order) {
    const i = lessons.findIndex((l) => l.state === st);
    if (i >= 0) return i;
  }
  return 0;
}

// --- DOM ------------------------------------------------------------------------------------

const SVG_NS = "http://www.w3.org/2000/svg";

function starSvg(on, size) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", `icon star ${on ? "star--on" : "star--off"}`);
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.style.width = svg.style.height = size;
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", "#i-star");
  svg.append(use);
  return svg;
}

function lockSvg() {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "icon node__lock");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", "#i-lock");
  svg.append(use);
  return svg;
}

/**
 * Малює вузли в контейнері layer. Повертає API: select(i), selected().
 * onSelect(i, lesson) — для панелі уроку (фаза 10).
 */
/**
 * Де поставити ярлик «Ти тут», щоб він не закрив сусідній вузол чи його зірки:
 * над вузлом → під ним → праворуч → ліворуч (перша вільна сторона; координати viewBox).
 */
export function tagSide(pos, all) {
  const near = (dx, dy) => all.some((o) => o !== pos && Math.abs(o.x - pos.x - dx) < 48 && Math.abs(o.y - pos.y - dy) < 40);
  if (!near(0, -62)) return "above";
  if (!near(0, 62)) return "below";
  if (!near(70, 0)) return "right";
  return "left";
}

export function renderNodes(layer, map, L, { onSelect } = {}) {
  layer.replaceChildren();
  const pct = (v, total) => `${((v / total) * 100).toFixed(3)}%`;
  const buttons = new Map();          // індекс уроку → кнопка (на телефоні — лише уроки групи)
  const order = [];                   // індекси уроків у порядку на мапі
  let current = -1;

  for (const pos of L.nodes) {
    const i = pos.lessonIdx, lesson = map.lessons[i];
    const isl = map.paragraphs[lesson.paraIdx].isl;
    const wrap = document.createElement("div");
    wrap.className = `node-wrap isl-${isl}`;
    wrap.style.setProperty("--x", pct(pos.x, L.width));
    wrap.style.setProperty("--y", pct(pos.y, L.height));

    if (lesson.state === "current") {
      const ring = document.createElement("span");
      ring.className = "node__ring";
      ring.setAttribute("aria-hidden", "true");
      const tag = document.createElement("span");
      tag.className = `node__tag node__tag--${tagSide(pos, L.nodes)}`;
      tag.setAttribute("aria-hidden", "true");
      tag.textContent = "Ти тут";
      wrap.append(ring, tag);
    }

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `node node--${lesson.state}`;
    btn.dataset.index = String(i);
    btn.setAttribute("aria-pressed", "false");
    btn.setAttribute("aria-label", nodeLabel(lesson));
    btn.tabIndex = -1;                 // «блукаючий» tabindex: одна зупинка Tab на мапу, далі — стрілки
    if (lesson.state === "locked") btn.append(lockSvg());
    else btn.textContent = String(lesson.number);
    wrap.append(btn);

    if (lesson.state === "done") {
      const stars = document.createElement("span");
      stars.className = "node__stars stars--outline";
      stars.setAttribute("aria-hidden", "true");
      for (let k = 0; k < 3; k++) stars.append(starSvg(k < lesson.stars, "calc(14px * var(--s, 1))"));
      wrap.append(stars);
    }
    layer.append(wrap);
    buttons.set(i, btn);
    order.push(i);
  }

  /** Зупинка Tab — на вибраному уроці (або на першому, поки нічого не вибрано на цьому шарі). */
  function setTabStop(i) {
    for (const b of buttons.values()) b.tabIndex = -1;
    const target = buttons.get(i) ?? buttons.get(order[0]);
    if (target) target.tabIndex = 0;
  }
  setTabStop(-1);

  /** Вибрати урок i (індекс у map.lessons). Якщо його немає на цьому шарі — лише запам’ятати. */
  function select(i, { focus = false, push = true, silent = false } = {}) {
    if (i < 0 || i >= map.lessons.length) return;
    buttons.get(current)?.setAttribute("aria-pressed", "false");
    current = i;
    const btn = buttons.get(i);
    btn?.setAttribute("aria-pressed", "true");
    setTabStop(i);
    if (focus) btn?.focus();
    if (push) history.replaceState(null, "", lessonHash(map.lessons[i]));
    if (!silent) onSelect?.(i, map.lessons[i]);
  }

  layer.addEventListener("click", (e) => {
    const btn = e.target.closest(".node");
    if (btn) select(Number(btn.dataset.index));
  });
  layer.addEventListener("dblclick", (e) => {
    const btn = e.target.closest(".node");
    if (!btn) return;
    const lesson = map.lessons[Number(btn.dataset.index)];
    if (canPlay(lesson)) location.href = playUrl(lesson);
  });
  layer.addEventListener("keydown", (e) => {
    const btn = e.target.closest(".node");
    if (!btn) return;
    const k = order.indexOf(Number(btn.dataset.index));
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); select(order[Math.min(k + 1, order.length - 1)], { focus: true }); }
    if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); select(order[Math.max(k - 1, 0)], { focus: true }); }
    if (e.key === "Home") { e.preventDefault(); select(order[0], { focus: true }); }
    if (e.key === "End") { e.preventDefault(); select(order[order.length - 1], { focus: true }); }
  });

  return { select, selected: () => current, buttons, order };
}

/** Ділянки, де всі уроки «у хмарах», і найбільша з них — для підказки. */
export function fogRegions(map, L) {
  const fog = L.regions.filter((r) => {
    const idx = map.paragraphs[r.paraIdx].lessonIdx;
    return idx.length > 0 && idx.every((i) => map.lessons[i].state === "soon");
  });
  const biggest = fog.reduce((best, r) => (!best || r.rx * r.ry > best.rx * best.ry ? r : best), null);
  return { fog, biggest };
}

// --- «Острів пройдено»: хмара розходиться при першому візиті після імпорту (фаза 20, FE-0632) ---

const fogSeenKey = (grade) => `mw_fog_seen_grade_${grade}`;

/** Id параграфів, що були в хмарі минулого візиту (`loadSeenFog`), а зараз уже ні. */
export function newlyRevealed(previousIds, currentIds) {
  if (!previousIds?.length) return [];
  const current = new Set(currentIds);
  return previousIds.filter((id) => !current.has(id));
}

/** Останній запам'ятований набір id параграфів у хмарі для класу. `null` — візит перший. */
export function loadSeenFog(grade) {
  try {
    const raw = globalThis.localStorage?.getItem(fogSeenKey(grade));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;   // приватне вікно, заблоковане сховище, биті дані
  }
}

export function saveSeenFog(grade, ids) {
  try {
    globalThis.localStorage?.setItem(fogSeenKey(grade), JSON.stringify(ids));
  } catch {
    /* приватне вікно — переживемо без пам'яті між візитами, просто без анімації */
  }
}

// --- Прохід стежкою від старого вузла до нового після фіналу (фаза 20, FE-0633) ------------

const JUST_FINISHED_KEY = "mw_just_finished";

/** Викликає play.js перед переходом на мапу, якщо урок щойно приніс нову зірку. Одноразово. */
export function markJustFinished(grade, lessonHash) {
  try {
    globalThis.sessionStorage?.setItem(JUST_FINISHED_KEY, JSON.stringify({ grade, lessonHash }));
  } catch {
    /* приватне вікно — переживемо без анімації проходу */
  }
}

/** Читає й одразу прибирає прапорець — спрацьовує рівно раз, навіть якщо клас не збігся. */
export function consumeJustFinished(grade) {
  try {
    const raw = globalThis.sessionStorage?.getItem(JUST_FINISHED_KEY);
    globalThis.sessionStorage?.removeItem(JUST_FINISHED_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    return data.grade === grade ? data.lessonHash : null;
  } catch {
    return null;
  }
}

/**
 * Індекси вузлів, якими «пройти» від `fromIndex` до `toIndex`: проміжні уроки «у хмарах»
 * пропускаємо (вони не на стежці по суті), а якщо кроків усе одно забагато — лише початок і кінець.
 */
export function walkSteps(lessons, fromIndex, toIndex) {
  const dir = fromIndex < toIndex ? 1 : -1;
  const steps = [fromIndex];
  for (let i = fromIndex + dir; i !== toIndex; i += dir) {
    if (lessons[i]?.state !== "soon") steps.push(i);
  }
  steps.push(toIndex);
  return steps.length > 6 ? [fromIndex, toIndex] : steps;
}
