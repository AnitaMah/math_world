// Мапа класу (фаза 8): дані → normalizeMap → layoutGrade → SVG.
// Вузли уроків — фаза 9, панель уроку — фаза 10, телефон — фаза 11.
import { api, normalizeMap } from "./api.js";
import { layoutGrade } from "./map-layout.js";
import {
  renderNodes, fogRegions, initialIndex, newlyRevealed, loadSeenFog, saveSeenFog,
  consumeJustFinished, walkSteps, findByHash,
} from "./map-nodes.js";
import { lessonListModel } from "./lesson-panel.js";
import { mountPanZoom } from "./map-pan.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const stage = document.getElementById("mapStage");
const canvas = document.getElementById("mapCanvas");
const sea = document.getElementById("sea");
const nodesLayer = document.getElementById("mapNodes");
const fogHint = document.getElementById("fogHint");
const minimap = document.getElementById("mapMinimap");
const minimapSvg = document.getElementById("mapMinimapSvg");
const minimapViewport = document.getElementById("mapMinimapViewport");
const show = (id) => {
  for (const el of ["mapLoading", "mapError", "mapEmpty"]) document.getElementById(el).hidden = el !== id;
  canvas.hidden = id !== null;
};

/** Рамка «ти тут» на мінімапі — частки (0–1) видимого в'юпорта (фаза 20, FE-0635). */
function updateMinimapViewport(rect) {
  minimapViewport.style.left = `${(rect.x * 100).toFixed(2)}%`;
  minimapViewport.style.top = `${(rect.y * 100).toFixed(2)}%`;
  minimapViewport.style.width = `${(rect.w * 100).toFixed(2)}%`;
  minimapViewport.style.height = `${(rect.h * 100).toFixed(2)}%`;
}

// Масштаб/панорамування на десктопі (фаза 20, FE-0634) — одне підключення на весь час життя сторінки
// (load() може виконатись повторно після «Спробувати ще раз»); кожне нове завантаження скидає вигляд.
const panZoom = mountPanZoom(stage, canvas, { onChange: updateMinimapViewport });

/** Острови й «ти тут» на мінімапі, тим самим viewBox, що й основна мапа. */
function renderMinimap(map, L) {
  minimapSvg.setAttribute("viewBox", L.viewBox);
  const idx = map.lessons.findIndex((l) => l.state === "current");
  const dot = idx >= 0 ? L.nodes[idx] : null;
  const r = Math.max(L.width, L.height) * 0.02;
  minimapSvg.innerHTML = L.islands.map((i) => `<path class="map-minimap__land" d="${i.d}"/>`).join("")
    + (dot ? `<circle class="map-minimap__dot" cx="${dot.x}" cy="${dot.y}" r="${r}"/>` : "");
}

/** Клік або перетягування по мінімапі переносить в'юпорт туди (масштаб лишається той самий). */
function mountMinimapNav() {
  const fraction = (e) => {
    const r = minimap.getBoundingClientRect();
    return { fx: (e.clientX - r.left) / r.width, fy: (e.clientY - r.top) / r.height };
  };
  let dragging = false;
  minimap.addEventListener("pointerdown", (e) => {
    dragging = true;
    minimap.setPointerCapture(e.pointerId);
    const { fx, fy } = fraction(e);
    panZoom.panToFraction(fx, fy);
  });
  minimap.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const { fx, fy } = fraction(e);
    panZoom.panToFraction(fx, fy);
  });
  const stop = () => { dragging = false; };
  minimap.addEventListener("pointerup", stop);
  minimap.addEventListener("pointercancel", stop);
}
mountMinimapNav();

/** Екранування тексту для вставки в розмітку. */
export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const ICONS = {
  ruler: `<g transform="rotate(-28)"><rect class="sea__icon" x="-35" y="-8" width="70" height="16" rx="3"/>
    <path class="sea__icon" d="M-25 -8v6M-15 -8v4M-5 -8v6M5 -8v4M15 -8v6M25 -8v4"/></g>`,
  triangle: `<path class="sea__icon" d="M0,-27 L34,27 L-34,27Z"/>`,
  cube: `<path class="sea__icon" d="M-22,-13 l22,-12 22,12 v26 l-22,12 -22,-12z M-22,-13 l22,12 22,-12 M0,-1 v26"/>`,
  pie: `<circle class="sea__icon" r="22"/><path class="sea__icon-fill" d="M0,0 V-22 A22,22 0 0,1 19,11 Z"/>`,
  decimal: `<text class="sea__icon-text" font-size="22">0,5</text>`,
  percent: `<text class="sea__icon-text" font-size="40">%</text>`,
  equation: `<text class="sea__icon-text" font-size="34" font-style="italic">x</text>`,
};

export function renderSea(map, L, fog = [], revealed = []) {
  const parts = [`<title id="seaTitle">Мапа ${esc(map.grade)} класу: острови-розділи і стежки уроків</title>`];
  parts.push(`<defs>${L.islands.map((i) => `<clipPath id="isl-clip-${i.sectionIdx}"><path d="${i.d}"/></clipPath>`).join("")}</defs>`);
  // 1–2. вода
  parts.push(`<g aria-hidden="true">${L.decor.waves.map((w) => `<path class="sea__wave" d="M${w.x},${w.y} q7,-7 14,0 t14,0 t14,0"/>`).join("")}`
    + `${L.decor.specks.map((p) => `<circle class="sea__speck" cx="${p.x}" cy="${p.y}" r="${p.r}"/>`).join("")}</g>`);
  // 3–5. острови: мілина, берег, ділянки параграфів (обрізані контуром острова)
  parts.push(`<g aria-hidden="true">${L.islands.map((i) => `<path class="sea__shallow" d="${i.d}"/>`).join("")}</g>`);
  parts.push(`<g aria-hidden="true">${L.islands.map((i) => `<path class="sea__rim" d="${i.d}"/>`).join("")}</g>`);
  parts.push(`<g aria-hidden="true">${L.regions.map((r) => `<path class="sea__land isl-${r.isl}" d="${r.d}" clip-path="url(#isl-clip-${r.sectionIdx})"/>`).join("")}</g>`);
  // 6. піктограми на суші
  parts.push(`<g aria-hidden="true">${L.decor.icons.map((ic) => `<g class="isl-${ic.isl}" transform="translate(${ic.x} ${ic.y})">${ICONS[ic.kind] ?? ""}</g>`).join("")}</g>`);
  // 7–8. стежки, переходи між параграфами, маршрут човна
  parts.push(`<g aria-hidden="true">${L.routes.map((r) => `<path class="sea__route" d="${r.d}"/>`).join("")}`
    + `${L.connectors.map((c) => `<path class="${c.kind === "boat" ? "sea__boat-route" : "sea__route"}" d="${c.d}"/>`).join("")}`
    + `${L.connectors.filter((c) => c.boat).map((c) => `<use class="sea__boat" href="#i-boat" x="${c.boat.x - 16}" y="${c.boat.y - 18}" width="32" height="32"/>`).join("")}</g>`);
  // 9. хмари над параграфами, яких ще немає в БД
  parts.push(`<g aria-hidden="true">${fog.map((r) => `<path class="sea__fog" d="${r.d}"/>`).join("")}</g>`);
  // 9.5. «острів пройдено»: хмара над щойно імпортованим параграфом — показуємо й одразу розганяємо
  parts.push(`<g aria-hidden="true">${revealed.map((r) => `<path class="sea__fog sea__fog--reveal" d="${r.d}"/>`).join("")}</g>`);
  // чіпи параграфів / розділів
  parts.push(`<g class="sea__chips">${L.chips.map((c) => {
    const isl = c.isl ? `isl-${c.isl}` : "";
    const badgeCls = c.isl ? "sea__chip-badge" : "sea__chip-badge sea__chip-badge--section";
    return `<g class="sea__chip ${isl}" transform="translate(${c.x} ${c.y})">
      <rect class="sea__chip-bg" width="${c.w}" height="${c.h}" rx="${c.h / 2}"/>
      <rect class="${badgeCls}" x="5" y="5" width="10" height="${c.h - 10}" rx="${(c.h - 10) / 2}"/>
      <text class="sea__chip-badge-text" x="13" y="${c.h / 2}">${esc(c.badge)}</text>
      <text class="sea__chip-text" x="0" y="${c.h / 2}">${esc(c.text)}</text></g>`;
  }).join("")}</g>`);
  return parts.join("");
}

/** Підганяє ширину чіпів під справжню ширину тексту (шрифт уже завантажено). */
function fitChips() {
  for (const chip of sea.querySelectorAll(".sea__chip")) {
    const [bg, badge] = chip.querySelectorAll("rect");
    const [badgeText, text] = chip.querySelectorAll("text");
    const bw = badgeText.getComputedTextLength();
    badge.setAttribute("width", String(Math.ceil(bw + 16)));
    const textX = 5 + bw + 16 + 8;
    text.setAttribute("x", String(Math.round(textX)));
    bg.setAttribute("width", String(Math.ceil(textX + text.getComputedTextLength() + 12)));
  }
}

const WALK_HOP_MS = 420;

/** Прохід стежкою від одного вузла до іншого — кілька «кроків» по позиції (фаза 20, FE-0633). */
async function walkTo(map, L, fromIndex, toIndex) {
  if (globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;   // без руху — одразу обираємо toIndex нижче
  const steps = walkSteps(map.lessons, fromIndex, toIndex).map((i) => L.nodes[i]).filter(Boolean);
  if (steps.length < 2) return;
  const pct = (v, total) => `${((v / total) * 100).toFixed(3)}%`;
  const walker = document.createElement("div");
  walker.className = `map-walker isl-${map.paragraphs[map.lessons[toIndex].paraIdx].isl}`;
  walker.setAttribute("aria-hidden", "true");
  walker.style.setProperty("--x", pct(steps[0].x, L.width));
  walker.style.setProperty("--y", pct(steps[0].y, L.height));
  nodesLayer.append(walker);
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));   // застосувати старт до першого переходу
  for (const pos of steps.slice(1)) {
    walker.style.setProperty("--x", pct(pos.x, L.width));
    walker.style.setProperty("--y", pct(pos.y, L.height));
    await new Promise((r) => setTimeout(r, WALK_HOP_MS));
  }
  walker.remove();
}

async function load() {
  show("mapLoading");
  panZoom.reset();
  const grade = Number(stage.dataset.grade);
  const res = await api.gradeMap(grade);
  if (!res.ok) {
    document.getElementById("mapErrorText").textContent = res.data?.detail || "Перевір з’єднання і спробуй ще раз.";
    return show("mapError");
  }
  const map = normalizeMap(res.data);
  if (!map.lessons.length) return show("mapEmpty");
  const L = layoutGrade(map);
  sea.setAttribute("viewBox", L.viewBox);
  canvas.style.setProperty("--ar", (L.width / L.height).toFixed(4));
  stage.style.setProperty("--ar", (L.width / L.height).toFixed(4));   // мінімапа — сестра canvas, читає з stage
  renderMinimap(map, L);
  const { fog, biggest } = fogRegions(map, L);
  const fogIds = fog.map((r) => map.paragraphs[r.paraIdx].id);
  const revealedIds = newlyRevealed(loadSeenFog(map.grade), fogIds);
  const revealed = revealedIds.length
    ? L.regions.filter((r) => revealedIds.includes(map.paragraphs[r.paraIdx].id))
    : [];
  sea.innerHTML = renderSea(map, L, fog, revealed);
  saveSeenFog(map.grade, fogIds);
  // підказка — одна на мапу, у центрі найбільшої хмари
  fogHint.hidden = !biggest;
  if (biggest) {
    fogHint.style.setProperty("--x", `${((biggest.cx / L.width) * 100).toFixed(3)}%`);
    fogHint.style.setProperty("--y", `${((biggest.cy / L.height) * 100).toFixed(3)}%`);
  }
  // масштаб вузлів = ширина полотна / ширина viewBox
  new ResizeObserver(() => canvas.style.setProperty("--s", (canvas.clientWidth / L.width).toFixed(4))).observe(canvas);
  const nodes = renderNodes(nodesLayer, map, L, {
    onSelect: (i, lesson) => stage.dispatchEvent(new CustomEvent("lesson:select", { detail: { index: i, lesson, map } })),
  });
  show(null);
  await document.fonts.ready;
  fitChips();
  nodes.select(initialIndex(map.lessons, location.hash), { push: false });
  // вибір на телефоні → тихо синхронізувати десктопні вузли (без повторної події)
  stage.addEventListener("lesson:select", (e) => {
    if (e.detail.source === "mobile") nodes.select(e.detail.index, { silent: true, push: true });
  });
  renderLessonList(map);
  stage.dispatchEvent(new CustomEvent("map:ready", { detail: { map, layout: L, nodes } }));

  // щойно пройшов урок і відкрив наступний (play.js, finish()) — пройти стежкою до нього на очах
  const finishedHash = consumeJustFinished(grade);
  if (finishedHash) {
    const fromIndex = findByHash(map.lessons, finishedHash);
    const toIndex = map.lessons.findIndex((l) => l.state === "current");
    if (fromIndex >= 0 && toIndex >= 0 && toIndex !== fromIndex && map.lessons[fromIndex].state === "done") {
      await walkTo(map, L, fromIndex, toIndex);
      nodes.select(toIndex, { focus: true });
    }
  }
}

/** Прихований для очей список усіх уроків — текстова альтернатива мапи для скрінрідера. */
function renderLessonList(map) {
  const nav = document.getElementById("lessonList");
  if (!nav) return;
  const title = document.createElement("h2");
  title.textContent = "Усі уроки списком";
  const groups = lessonListModel(map).map((g) => {
    const h = document.createElement("h3");
    h.textContent = g.heading;
    const ol = document.createElement("ol");
    for (const l of g.lessons) {
      const li = document.createElement("li");
      if (l.href) {
        const a = document.createElement("a");
        a.href = l.href;
        a.tabIndex = -1;            // для скрінрідера (режим читання); Tab — по видимих елементах
        a.textContent = l.text;
        li.append(a);
      } else li.textContent = l.text;
      ol.append(li);
    }
    return [h, ol];
  });
  nav.replaceChildren(title, ...groups.flat());
}

document.getElementById("mapRetry").addEventListener("click", load);
load();
