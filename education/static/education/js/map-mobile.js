// Мапа на телефоні (фаза 11): один острів-параграф на екран, стежка згори вниз, нижній лист уроку,
// список островів, перехід між параграфами кнопками й свайпом. Активна при ширині ≤ 720 px.
import { layoutLessons } from "./map-layout.js";
import { renderNodes } from "./map-nodes.js";
import { islandRows, panelModel } from "./lesson-panel.js";
import { plural } from "./ui.js";

export const PHONE = "(max-width: 720px)";

/** Групи для телефону = рядки «Острови класу»: параграф, або розділ, якщо урок = §. */
export function groupsOf(map) {
  return islandRows(map);
}
export function groupOfLesson(groups, lessonIdx) {
  return Math.max(0, groups.findIndex((g) => g.lessons.includes(lessonIdx)));
}

/** «Розділ I · 3 з 6 уроків · 8 / 18 ★» — підзаголовок картки групи. */
export function groupMeta(map, g) {
  const S = map.sections[g.sectionIdx];
  const unit = g.kind === "section" ? ["параграф", "параграфи", "параграфів"] : ["урок", "уроки", "уроків"];
  const head = g.kind === "section" ? `${g.lessons.length} ${plural(g.lessons.length, unit)}` : `Розділ ${S.roman} · ${g.done} з ${g.lessons.length} ${plural(g.lessons.length, unit)}`;
  return g.fog ? `${head} · ще в хмарах` : `${head} · ${g.score}`;
}

/** Свайп: горизонтальний рух ≥ 60 px, і по горизонталі більше, ніж по вертикалі. */
export function swipeDirection(dx, dy) {
  if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return 0;
  return dx < 0 ? 1 : -1;   // вліво → наступний, вправо → попередній
}

/** Свайп вниз (а не вбік і не дотик) — згортає розгорнутий нижній лист уроку (фаза 11, FE-0455). */
export function swipeDown(dx, dy) {
  return dy > 60 && Math.abs(dy) > Math.abs(dx) * 1.5;
}

const $ = (root, sel) => root.querySelector(sel);
const SVG_NS = "http://www.w3.org/2000/svg";

export function mountMobile(root, stage) {
  const mq = matchMedia(PHONE);
  const canvas = $(root, "#mmCanvas"), sea = $(root, "#mmSea"), layer = $(root, "#mmNodes");
  const scroll = $(root, "#mmScroll"), sheet = $(root, "#lessonSheet");
  const dialog = document.getElementById("islandsSheet");
  let map = null, groups = [], groupIdx = -1, nodes = null, selected = -1, L = null;

  new ResizeObserver(() => { if (L) canvas.style.setProperty("--s", (canvas.clientWidth / L.width).toFixed(4)); }).observe(canvas);
  // відступ прокрутки = справжня висота нижнього листа (розгорнутий лист вищий), щоб він нічого не закривав
  new ResizeObserver(() => root.style.setProperty("--sheet-h", `${sheet.offsetHeight + 8}px`)).observe(sheet);

  function emit(i) {
    stage.dispatchEvent(new CustomEvent("lesson:select", { detail: { index: i, lesson: map.lessons[i], map, source: "mobile" } }));
  }

  function renderGroup(gi, { scrollTo = true } = {}) {
    groupIdx = gi;
    const g = groups[gi];
    L = layoutLessons(map, g.lessons, { isl: g.isl, key: gi });
    sea.setAttribute("viewBox", L.viewBox);
    canvas.style.setProperty("--ar", (L.width / L.height).toFixed(4));
    canvas.style.setProperty("--s", (canvas.clientWidth / L.width).toFixed(4));
    sea.innerHTML = `<path class="sea__shallow" d="${L.island}"/><path class="sea__rim" d="${L.island}"/>`
      + `<path class="sea__land isl-${g.isl}" d="${L.island}" transform="translate(${L.width / 2} ${L.height / 2}) scale(.94) translate(${-L.width / 2} ${-L.height / 2})"/>`
      + (L.route ? `<path class="sea__route" d="${L.route}"/>` : "")
      + (g.fog ? `<path class="sea__fog" d="${L.island}"/>` : "");
    nodes = renderNodes(layer, map, L, { onSelect: (i) => emit(i) });
    if (selected >= 0) nodes.select(selected, { silent: true, push: false });

    $(root, "[data-f=badge]").textContent = g.badge;
    $(root, "[data-f=badge]").className = `mm-card__badge isl-${g.isl}`;
    $(root, "[data-f=title]").textContent = g.title;
    $(root, "[data-f=meta]").textContent = groupMeta(map, g);
    const prev = groups[gi - 1], next = groups[gi + 1];
    const prevBtn = $(root, "[data-f=prev]"), nextBtn = $(root, "[data-f=next]");
    prevBtn.hidden = !prev; nextBtn.hidden = !next;
    if (prev) $(prevBtn, "span").textContent = `${prev.badge} ${prev.title}`;
    if (next) $(nextBtn, "span").textContent = `Далі: ${next.badge} ${next.title}`;
    if (scrollTo) scrollToLesson(selected);
  }

  function scrollToLesson(i) {
    const btn = nodes?.buttons.get(i);
    if (!btn) { scroll.scrollTop = 0; return; }
    requestAnimationFrame(() => {
      const r = btn.getBoundingClientRect(), s = scroll.getBoundingClientRect();
      scroll.scrollTop += r.top - s.top - s.height * 0.4;
    });
  }

  /** `#para-<id>` замість `#lesson-<id>` (фаза 11, FE-0448): це перехід між параграфами, а не
      вибір конкретного уроку — emit() вище вже поставив `#lesson-…`, тут навмисно перебиваємо. */
  function setParaHash(g) {
    if (g.kind === "paragraph" && g.paraIdx != null) history.replaceState(null, "", `#para-${map.paragraphs[g.paraIdx].id}`);
  }

  /** 250 мс зсув острова при переході між параграфами (фаза 11, FE-0447); `prefers-reduced-motion`
      скорочує тривалість до миті глобальним правилом у base.css. */
  function slideCanvas(direction) {
    canvas.classList.remove("is-sliding-next", "is-sliding-prev");
    void canvas.offsetWidth;   // форсувати reflow — інакше повторний свайп у той самий бік не перезапустить анімацію
    canvas.classList.add(direction > 0 ? "is-sliding-next" : "is-sliding-prev");
  }

  function go(delta) {
    const gi = groupIdx + delta;
    if (gi < 0 || gi >= groups.length) return;
    const g = groups[gi];
    renderGroup(gi, { scrollTo: false });
    scroll.scrollTop = 0;
    slideCanvas(delta);
    emit(g.target);
    setParaHash(g);
  }

  // --- нижній лист уроку ---------------------------------------------------------------
  function fillSheet(i) {
    const m = panelModel(map, i);
    sheet.className = `lesson-sheet isl-${m.isl}${sheet.classList.contains("is-open") ? " is-open" : ""}`;
    const l = map.lessons[i], P = map.paragraphs[l.paraIdx];
    $(sheet, "[data-f=kicker]").textContent = l.kind === "paragraph" ? `§${P.number}` : `Урок ${l.number} · §${P.number}`;
    $(sheet, "[data-f=title]").textContent = m.title;
    const stars = $(sheet, "[data-f=stars]");
    stars.setAttribute("aria-label", m.starsLabel);
    stars.replaceChildren(...[0, 1, 2].map((k) => {
      const svg = document.createElementNS(SVG_NS, "svg");
      svg.setAttribute("class", `icon star ${k < m.stars ? "star--on" : "star--off"}`);
      svg.setAttribute("width", "20"); svg.setAttribute("height", "20"); svg.setAttribute("aria-hidden", "true");
      const use = document.createElementNS(SVG_NS, "use"); use.setAttribute("href", "#i-star"); svg.append(use);
      return svg;
    }));
    const bar = $(sheet, "[data-f=progress]");
    bar.setAttribute("aria-valuenow", String(m.solved)); bar.setAttribute("aria-valuemax", String(m.total));
    $(bar, ".progress__fill").style.setProperty("--p", `${m.total ? Math.round((m.solved / m.total) * 100) : 0}%`);
    $(sheet, "[data-f=count]").textContent = m.total ? `${m.solved} з ${m.total}` : "—";
    $(sheet, "[data-f=tasks]").textContent = m.hasTasks
      ? [m.autoText, m.showAi ? m.aiText : ""].filter(Boolean).join(" · ")
      : "Вправи ще не імпортовано з підручника";
    const slot = $(sheet, "[data-f=cta]");
    const cta = m.cta.href ? document.createElement("a") : document.createElement("button");
    cta.className = `btn btn--block btn--${m.cta.style}`;
    cta.textContent = m.cta.text;
    if (m.cta.href) cta.href = m.cta.href; else { cta.type = "button"; cta.setAttribute("aria-disabled", "true"); }
    slot.replaceChildren(cta);
    $(sheet, "[data-f=blocks]").replaceChildren(...m.blocks.map((b) => {
      const t = document.createElement("span"); t.className = "tag"; t.textContent = b; return t;
    }));
    $(sheet, "[data-f=theory]").href = m.theoryHref;
  }

  function setSheetOpen(open) {
    sheet.classList.toggle("is-open", open);
    $(sheet, "[data-f=toggle]").setAttribute("aria-expanded", String(open));
  }
  $(sheet, "[data-f=toggle]").addEventListener("click", () => setSheetOpen(!sheet.classList.contains("is-open")));

  // свайп вниз по розгорнутому листу — згортає (фаза 11, FE-0455)
  let sheetStart = null;
  sheet.addEventListener("pointerdown", (e) => { sheetStart = { x: e.clientX, y: e.clientY }; });
  sheet.addEventListener("pointerup", (e) => {
    if (!sheetStart) return;
    const down = swipeDown(e.clientX - sheetStart.x, e.clientY - sheetStart.y);
    sheetStart = null;
    if (down && sheet.classList.contains("is-open")) setSheetOpen(false);
  });

  // --- список островів ---------------------------------------------------------------------
  function fillDialog() {
    const list = $(dialog, "[data-f=list]");
    let lastSection = -1;
    list.replaceChildren(...groups.flatMap((g, gi) => {
      const out = [];
      if (g.sectionIdx !== lastSection) {
        lastSection = g.sectionIdx;
        const h = document.createElement("li");
        h.className = "label-caps islands-sheet__section";
        h.textContent = `Розділ ${map.sections[g.sectionIdx].roman} · ${map.sections[g.sectionIdx].shortTitle}`;
        out.push(h);
      }
      const row = document.getElementById("tpl-island-pick").content.firstElementChild.cloneNode(true);
      row.classList.add(`isl-${g.isl}`);
      if (g.fog) row.classList.add("is-fog");
      $(row, "[data-f=badge]").textContent = g.badge;
      $(row, "[data-f=title]").textContent = g.title;
      $(row, "[data-f=score]").textContent = g.fog ? "ще в хмарах" : g.score;
      $(row, ".progress__fill").style.setProperty("--p", `${g.max ? Math.round((g.got / g.max) * 100) : 0}%`);
      const btn = $(row, "button");
      if (gi === groupIdx) btn.setAttribute("aria-current", "true");
      btn.addEventListener("click", () => { dialog.close(); go(gi - groupIdx); });
      out.push(row);
      return out;
    }));
  }
  $(root, "[data-f=all]").addEventListener("click", () => { fillDialog(); dialog.showModal(); });
  $(dialog, "[data-f=close]").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => $(root, "[data-f=all]").focus());

  $(root, "[data-f=prev]").addEventListener("click", () => go(-1));
  $(root, "[data-f=next]").addEventListener("click", () => go(1));

  let start = null;
  scroll.addEventListener("pointerdown", (e) => { start = { x: e.clientX, y: e.clientY }; });
  scroll.addEventListener("pointerup", (e) => {
    if (!start) return;
    const dir = swipeDirection(e.clientX - start.x, e.clientY - start.y);
    start = null;
    if (dir) go(dir);
  });

  // --- зв’язок із мапою ---------------------------------------------------------------------
  stage.addEventListener("map:ready", (e) => {
    map = e.detail.map;
    groups = groupsOf(map);
    selected = e.detail.nodes.selected();
    if (mq.matches) { renderGroup(groupOfLesson(groups, selected)); fillSheet(selected); }
    root.hidden = false;
  });
  stage.addEventListener("lesson:select", (e) => {
    if (!map) return;
    selected = e.detail.index;
    if (!mq.matches) return;
    const gi = groupOfLesson(groups, selected);
    if (gi !== groupIdx) renderGroup(gi);
    else nodes?.select(selected, { silent: true, push: false });
    fillSheet(selected);
  });
  mq.addEventListener("change", () => {
    if (map && mq.matches) { renderGroup(groupOfLesson(groups, selected)); fillSheet(selected); }
  });
}

const root = globalThis.document?.getElementById("mapMobile");
const stage = globalThis.document?.getElementById("mapStage");
if (root && stage) mountMobile(root, stage);
