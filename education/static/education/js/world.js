// «Світ» (фаза 12): мініатюри архіпелагів і прогрес гравця на картках класів.
// Каркас карток рендерить сервер (дані з БД), тож сторінка працює й без JS; JS лише додає мапи й зірки.
import { api, normalizeMap } from "./api.js";
import { layoutGrade } from "./map-layout.js";
import { plural } from "./ui.js";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/** Що показати на картці класу. */
export function gradeSummary(map) {
  const playable = map.lessons.filter((l) => l.total > 0);
  const stars = map.lessons.reduce((s, l) => s + l.stars, 0);
  const current = map.lessons.find((l) => l.state === "current")
    ?? map.lessons.find((l) => l.state === "open") ?? null;
  const unit = current?.kind === "paragraph" ? "параграф" : "урок";
  let cta = "Відкрити мапу";
  if (current && stars === 0 && current.number === playable[0]?.number) cta = `Почати з ${unit}у ${current.number}`;
  else if (current) cta = `Продовжити · ${unit} ${current.number}`;
  return { building: playable.length === 0, stars, max: map.lessons.length * 3, cta };
}

/** Мініатюра: острови й ділянки + точки уроків (пройдені — колір острова, поточний — білий). */
export function miniSvg(map, L, building) {
  const parts = [`<defs>${L.islands.map((i) => `<clipPath id="w${map.grade}-${i.sectionIdx}"><path d="${i.d}"/></clipPath>`).join("")}</defs>`];
  parts.push(L.islands.map((i) => `<path class="${building ? "mini__rim mini__rim--building" : "mini__rim"}" d="${i.d}"/>`).join(""));
  if (building) {
    parts.push(L.islands.map((i) => `<text class="mini__num" x="${i.rect.x + i.rect.w / 2}" y="${i.rect.y + i.rect.h / 2}">${esc(map.sections[i.sectionIdx].roman)}</text>`).join(""));
    return parts.join("");
  }
  parts.push(L.regions.map((r) => `<path class="mini__land isl-${r.isl}" d="${r.d}" clip-path="url(#w${map.grade}-${r.sectionIdx})"/>`).join(""));
  parts.push(L.nodes.map((n) => {
    const l = map.lessons[n.lessonIdx], isl = map.paragraphs[l.paraIdx].isl;
    const cls = l.state === "current" ? "mini__dot mini__dot--current" : l.state === "done" ? `mini__dot mini__dot--done isl-${isl}` : "mini__dot";
    return `<circle class="${cls}" cx="${n.x}" cy="${n.y}" r="${l.state === "current" ? 22 : 15}"/>`;
  }).join(""));
  return parts.join("");
}

async function fill(li) {
  const n = Number(li.dataset.grade);
  const res = await api.gradeMap(n);
  if (!res.ok) return;
  const map = normalizeMap(res.data);
  if (!map.lessons.length) return;
  const L = layoutGrade(map);
  const s = gradeSummary(map);
  const svg = li.querySelector("[data-f=mini]");
  svg.setAttribute("viewBox", L.viewBox);
  svg.innerHTML = miniSvg(map, L, s.building);
  const q = (f) => li.querySelector(`[data-f=${f}]`);
  li.classList.toggle("is-building", s.building);
  q("building").hidden = !s.building;
  q("note").hidden = !s.building;
  q("stars-chip").hidden = s.building;
  q("stars").textContent = s.stars;
  q("max").textContent = s.max;
  q("stars-chip").setAttribute("aria-label", `${s.stars} ${plural(s.stars, ["зірка", "зірки", "зірок"])} з ${s.max}`);
  q("cta").hidden = s.building;
  q("cta").textContent = s.cta;
}

for (const li of globalThis.document?.querySelectorAll(".world-grade[data-grade]") ?? []) fill(li);
