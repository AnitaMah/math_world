// Екран «Прогрес» (фаза 20, беклог FE-0630): зірки по параграфах для кожного класу.
// Каркас карток класів рендерить сервер (дані з БД); цей модуль лише заповнює зірки
// й рядки параграфів із /api/grades/<n>/map/ (або моку) — так само, як world.js і lesson-panel.js.
import { api, normalizeMap } from "./api.js";
import { islandRows } from "./lesson-panel.js";
import { lessonHash } from "./map-nodes.js";
import { plural } from "./ui.js";

async function fillGrade(section) {
  const n = Number(section.dataset.grade);
  const q = (f) => section.querySelector(`[data-f=${f}]`);
  const res = await api.gradeMap(n);
  if (!res.ok) return;
  const map = normalizeMap(res.data);
  const rows = islandRows(map);
  if (!map.lessons.length || !rows.length) {
    q("empty").hidden = false;
    return;
  }

  const stars = map.lessons.reduce((s, l) => s + l.stars, 0);
  const max = map.lessons.length * 3;
  q("stars").textContent = stars;
  q("max").textContent = max;
  const chip = q("stars-chip");
  chip.hidden = false;
  chip.setAttribute("aria-label", `${stars} ${plural(stars, ["зірка", "зірки", "зірок"])} з ${max}`);

  const mapUrl = `/grades/${n}/`;
  q("rows").replaceChildren(...rows.map((r) => {
    const li = document.getElementById("tpl-progress-row").content.firstElementChild.cloneNode(true);
    li.classList.add(`isl-${r.isl}`);
    const link = li.querySelector("a");
    link.href = mapUrl + lessonHash(map.lessons[r.target]);
    link.setAttribute("aria-label", `${r.label}: ${r.score}. Перейти до уроку на мапі`);
    li.querySelector("[data-f=label]").textContent = r.label;
    li.querySelector("[data-f=score]").textContent = r.score;
    const bar = link.querySelector(".progress");
    bar.setAttribute("aria-valuenow", String(r.got));
    bar.setAttribute("aria-valuemax", String(r.max));
    bar.querySelector(".progress__fill").style.setProperty("--p", `${r.max ? Math.round((r.got / r.max) * 100) : 0}%`);
    return li;
  }));
}

for (const section of document.querySelectorAll(".progress-grade[data-grade]")) fillGrade(section);
