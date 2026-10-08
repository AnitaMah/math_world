// Мапа класу (фаза 8): дані → normalizeMap → layoutGrade → SVG.
// Вузли уроків — фаза 9, панель уроку — фаза 10, телефон — фаза 11.
import { api, normalizeMap } from "./api.js";
import { layoutGrade } from "./map-layout.js";
import { renderNodes, fogRegions, initialIndex } from "./map-nodes.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const stage = document.getElementById("mapStage");
const canvas = document.getElementById("mapCanvas");
const sea = document.getElementById("sea");
const nodesLayer = document.getElementById("mapNodes");
const fogHint = document.getElementById("fogHint");
const show = (id) => {
  for (const el of ["mapLoading", "mapError", "mapEmpty"]) document.getElementById(el).hidden = el !== id;
  canvas.hidden = id !== null;
};

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

export function renderSea(map, L, fog = []) {
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

async function load() {
  show("mapLoading");
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
  const { fog, biggest } = fogRegions(map, L);
  sea.innerHTML = renderSea(map, L, fog);
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
  stage.dispatchEvent(new CustomEvent("map:ready", { detail: { map, layout: L, nodes } }));
}

document.getElementById("mapRetry").addEventListener("click", load);
load();
