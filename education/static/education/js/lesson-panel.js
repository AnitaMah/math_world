// Панель уроку праворуч (фаза 10): що в уроці, зірки, кнопки, острови класу.
// Слухає події мапи: map:ready (острови класу) і lesson:select (вибраний урок).
import { plural } from "./ui.js";
import { playUrl, starsText } from "./map-nodes.js";

export const BLOCK_NAMES = {
  theory: "Теорія", self_check: "Перевір себе", oral_exercise: "Розв’язуємо усно", exercise: "Вправи",
  review_exercise: "Повторення", wise_owl: "Задача Мудрої Сови", history_aside: "Коли зроблено уроки",
};
const STATUS = {
  done: "Пройдено", current: "Ти тут", open: "Відкрито", locked: "Закрито", soon: "У хмарах",
};

/** Номер уроку, який треба пройти, щоб відкрився закритий: найближчий попередній урок із завданнями. */
export function blockingLesson(map, index) {
  for (let i = index - 1; i >= 0; i--) if (map.lessons[i].total > 0) return map.lessons[i];
  return null;
}

/** Куди веде «Читати теорію»: сторінка пункту або старий список § (поки немає нової сторінки §). */
export function theoryUrl(lesson) {
  return lesson.kind === "paragraph" ? `/paragraphs/${lesson.id}/items/` : `/items/${lesson.id}/`;
}

/** Усе, що панель показує для уроку, — без DOM (тестується в node). */
export function panelModel(map, index) {
  const l = map.lessons[index], P = map.paragraphs[l.paraIdx], S = map.sections[l.sectionIdx];
  const tasks = l.tasks ?? { auto: 0, ai: 0, approx: true };
  const approx = tasks.approx ? "≈ " : "";
  const cta = {
    done: { text: "Пройти ще раз", href: playUrl(l), style: "info" },
    current: { text: "Продовжити", href: playUrl(l), style: "primary" },
    open: { text: "Почати урок", href: playUrl(l), style: "primary" },
    locked: { text: `Спершу пройди урок ${blockingLesson(map, index)?.number ?? ""}`.trim(), href: null, style: "muted" },
    soon: { text: "Скоро", href: null, style: "muted" },
  }[l.state] ?? { text: "Скоро", href: null, style: "muted" };
  const lessonsTotal = map.lessons.filter((x) => x.kind === l.kind).length;
  return {
    isl: P.isl,
    section: `Розділ ${S.roman} · §${P.number} ${P.shortTitle}`,
    title: l.kind === "paragraph" ? P.shortTitle : l.title,
    status: STATUS[l.state] ?? l.state,
    state: l.state,
    position: `${l.kind === "paragraph" ? "Параграф" : "Урок"} ${l.number} з ${lessonsTotal}`,
    stars: l.stars,
    starsLabel: starsText(l.stars),
    hasTasks: l.total > 0,
    solved: l.solved,
    total: l.total,
    solvedText: l.total > 0 ? `Розв’язано ${l.solved} з ${l.total}` : "Завдань поки немає",
    autoText: `${approx}${tasks.auto} ${plural(tasks.auto, ["вправа", "вправи", "вправ"])} з автоперевіркою`,
    aiText: `${tasks.ai} ${plural(tasks.ai, ["текстова задача", "текстові задачі", "текстових задач"])} з ШІ`,
    showAi: tasks.ai > 0,
    approx: tasks.approx,
    blocks: (l.blocks ?? []).map((b) => BLOCK_NAMES[b]).filter(Boolean),
    cta,
    theoryHref: theoryUrl(l),
  };
}

/** Рядки «Острови N класу»: по параграфу, або по розділу, якщо урок = § (6 клас). */
export function islandRows(map) {
  const rows = [];
  for (const S of map.sections) {
    const paras = S.paragraphIdx.map((p) => map.paragraphs[p]);
    const perSection = paras.length > 0 && paras.every((P) => P.lessonIdx.length <= 1);
    const groups = perSection
      ? [{ label: `Розділ ${S.roman} ${S.shortTitle}`, lessons: paras.flatMap((P) => P.lessonIdx), isl: paras[0]?.isl ?? 1 }]
      : paras.map((P) => ({ label: `${S.roman} · §${P.number} ${P.shortTitle}`, lessons: P.lessonIdx, isl: P.isl }));
    for (const g of groups) {
      const got = g.lessons.reduce((s, i) => s + map.lessons[i].stars, 0), max = g.lessons.length * 3;
      const target = g.lessons.find((i) => ["current", "open"].includes(map.lessons[i].state))
        ?? g.lessons.find((i) => map.lessons[i].state !== "soon") ?? g.lessons[0];
      rows.push({ label: g.label, score: `${got} / ${max} ★`, got, max, isl: g.isl, target });
    }
  }
  return rows;
}

// --- DOM ------------------------------------------------------------------------------------

const SVG_NS = "http://www.w3.org/2000/svg";
function star(on) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", `icon star ${on ? "star--on" : "star--off"}`);
  svg.setAttribute("width", "30"); svg.setAttribute("height", "30");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", "#i-star");
  svg.append(use);
  return svg;
}
const q = (root, sel) => root.querySelector(sel);

function setProgress(el, value, max) {
  el.setAttribute("aria-valuenow", String(value));
  el.setAttribute("aria-valuemax", String(max));
  q(el, ".progress__fill").style.setProperty("--p", `${max ? Math.round((value / max) * 100) : 0}%`);
}

export function mountPanel(panel, stage) {
  let state = { map: null, nodes: null };

  stage.addEventListener("map:ready", (e) => {
    state = { map: e.detail.map, nodes: e.detail.nodes };
    renderIslands();
    const i = state.nodes.selected();
    if (i >= 0) renderLesson(i);
  });
  stage.addEventListener("lesson:select", (e) => { if (state.map) renderLesson(e.detail.index); });

  function renderLesson(index) {
    const m = panelModel(state.map, index);
    const view = q(panel, "[data-panel=lesson]") ?? (() => {
      const node = document.getElementById("tpl-lesson-panel").content.firstElementChild.cloneNode(true);
      panel.prepend(node);
      q(panel, "[data-panel=hint]")?.remove();
      return node;
    })();
    panel.className = panel.className.replace(/\bisl-\d\b/g, "").trim() + ` isl-${m.isl}`;
    q(view, "[data-f=section]").textContent = m.section;
    q(view, "[data-f=title]").textContent = m.title;
    const status = q(view, "[data-f=status]");
    status.textContent = m.status;
    status.className = `status status--${m.state}`;
    q(view, "[data-f=position]").textContent = m.position;

    const stars = q(view, "[data-f=stars]");
    stars.replaceChildren(...[0, 1, 2].map((k) => star(k < m.stars)));
    stars.setAttribute("aria-label", m.starsLabel);
    q(view, "[data-f=solved]").textContent = m.solvedText;
    setProgress(q(view, "[data-f=progress]"), m.solved, m.total);

    q(view, "[data-f=tasks]").hidden = !m.hasTasks;
    q(view, "[data-f=empty]").hidden = m.hasTasks;
    q(view, "[data-f=auto]").textContent = m.autoText;
    q(view, "[data-f=auto]").title = m.approx ? "Приблизно: бекенд ще не віддає точну кількість завдань" : "";
    q(view, "[data-f=ai-row]").hidden = !m.showAi;
    q(view, "[data-f=ai]").textContent = m.aiText;
    q(view, "[data-f=blocks]").replaceChildren(...m.blocks.map((b) => {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = b;
      return tag;
    }));

    const slot = q(view, "[data-f=cta]");
    const cta = m.cta.href ? document.createElement("a") : document.createElement("button");
    cta.className = `btn btn--block btn--${m.cta.style}`;
    cta.textContent = m.cta.text;
    if (m.cta.href) cta.href = m.cta.href;
    else { cta.type = "button"; cta.setAttribute("aria-disabled", "true"); }
    slot.replaceChildren(cta);
    q(view, "[data-f=theory]").href = m.theoryHref;
  }

  function renderIslands() {
    const list = q(panel, "[data-f=islands]");
    q(panel, "[data-f=islands-title]").textContent = `Острови ${state.map.grade} класу`;
    list.replaceChildren(...islandRows(state.map).map((r) => {
      const row = document.getElementById("tpl-island-row").content.firstElementChild.cloneNode(true);
      row.classList.add(`isl-${r.isl}`);
      q(row, "[data-f=label]").textContent = r.label;
      q(row, "[data-f=score]").textContent = r.score;
      setProgress(q(row, ".progress"), r.got, r.max);
      q(row, "button").addEventListener("click", () => state.nodes.select(r.target, { focus: true }));
      q(row, "button").setAttribute("aria-label", `${r.label}: ${r.score}. Перейти до уроку на мапі`);
      return row;
    }));
    q(panel, "[data-panel=islands]").hidden = false;
  }
}

const panel = globalThis.document?.getElementById("lessonPanel");
const stage = globalThis.document?.getElementById("mapStage");
if (panel && stage) mountPanel(panel, stage);
