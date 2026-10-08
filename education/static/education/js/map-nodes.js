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
export function renderNodes(layer, map, L, { onSelect } = {}) {
  layer.replaceChildren();
  const pct = (v, total) => `${((v / total) * 100).toFixed(3)}%`;
  const buttons = [];
  let current = -1;

  map.lessons.forEach((lesson, i) => {
    const pos = L.nodes[i];
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
      tag.className = "node__tag";
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
    buttons.push(btn);
  });

  function select(i, { focus = false, push = true } = {}) {
    if (i < 0 || i >= buttons.length) return;
    if (current >= 0) buttons[current].setAttribute("aria-pressed", "false");
    current = i;
    buttons[i].setAttribute("aria-pressed", "true");
    if (focus) buttons[i].focus();
    if (push) history.replaceState(null, "", lessonHash(map.lessons[i]));
    onSelect?.(i, map.lessons[i]);
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
    const i = Number(btn.dataset.index);
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); select(Math.min(i + 1, buttons.length - 1), { focus: true }); }
    if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); select(Math.max(i - 1, 0), { focus: true }); }
  });

  return { select, selected: () => current, buttons };
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
