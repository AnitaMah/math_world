// Екран гри в новому UI (фаза 14). Дані — /api/play/… через api.js, логіка — play-core.js.
// Стани: loading → answer ⇄ busy → next → … → finish. Колір — острів уроку (isl-N на body).
import { api } from "./api.js";
import { errorFeedback, feedbackFor, finishModel, orderTasks, progressPct, taskView } from "./play-core.js";
import { markJustFinished } from "./map-nodes.js";

const root = document.getElementById("play");
const $ = (id) => document.getElementById(id);
const stage = $("stage"), actions = $("actions");
const fb = $("feedback"), fbIcon = $("feedbackIcon"), fbTitle = $("feedbackTitle"), fbText = $("feedbackText");
const { kind, lesson: lessonId, map: mapUrl, theory: theoryUrl, next: nextUrl, grade } = root.dataset;
const lessonHash = `#lesson-${kind === "paragraph" ? "p" : ""}${lessonId}`;

const AUTO_SKIP_MS = 2500;
let tasks = [], order = [], pos = 0, state = "loading", sessionPoints = 0, progress = null, startStars = 0;
let justEarnedStar = false;
let mainBtn = $("mainBtn"), skipBtn = $("skipBtn");

// нова зірка на фіналі могла відкрити наступний урок — мапа покаже прохід стежкою до нього
// (map.js, фаза 20, FE-0633); спрацьовує з обох виходів на мапу — кнопки й хрестика вгорі
function maybeMarkFinished() {
  if (justEarnedStar && grade) markJustFinished(Number(grade), lessonHash);
}
$("closeBtn")?.addEventListener("click", maybeMarkFinished);

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (name, size = 20, cls = "") =>
  `<svg class="icon icon--${name} ${cls}" width="${size}" height="${size}" aria-hidden="true" focusable="false"><use href="#i-${name}"/></svg>`;
const reduceMotion = () => globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// --- Верх ------------------------------------------------------------------------------

function setProgress() {
  const pct = progressPct(tasks);
  $("progressFill").style.setProperty("--p", pct + "%");
  root.querySelector(".progress").setAttribute("aria-valuenow", pct);
}

function updateMe(data) {
  const detail = {};
  if (data.total_points !== undefined) detail.points = data.total_points;
  if (data.streak !== undefined) detail.streak = data.streak;
  if (Object.keys(detail).length) document.dispatchEvent(new CustomEvent("me:updated", { detail }));
}

// --- Відгук ----------------------------------------------------------------------------

function showFeedback(f) {
  fb.className = `feedback feedback--${f.kind}`;
  fbIcon.innerHTML = icon(f.kind === "ok" ? "check" : f.kind === "info" ? "sparkle" : "close", 22);
  fbTitle.innerHTML = esc(f.title) + (f.points ? ` <span class="feedback__pts">${icon("bolt", 16)}+${f.points}</span>` : "");
  fbText.textContent = f.text || "";
  fb.hidden = false;
}

const hideFeedback = () => { fb.hidden = true; fb.className = "feedback"; };

function setMain(text, variant = "primary", disabled = false) {
  mainBtn.textContent = text;
  mainBtn.className = `btn btn--${variant} btn--block game__main`;
  mainBtn.disabled = disabled;
}

// --- Завдання --------------------------------------------------------------------------

function render() {
  hideFeedback();
  if (pos >= order.length) return finish();
  state = "answer";
  const v = taskView(tasks[order[pos]]);
  const badge = v.isAi
    ? `<span class="badge-ai">${icon("sparkle", 14)}ШІ перевірить</span>`
    : v.diff ? `<span class="diff diff--${v.diff.code}">${v.diff.name}</span>` : "";
  const figs = v.figures.map((f) =>
    `<figure class="lfigure"><img src="${esc(f.url)}" alt="${esc(f.label || "Рисунок")}">${f.label ? `<figcaption>${esc(f.label)}</figcaption>` : ""}</figure>`).join("");
  const question = v.question
    ? `<div class="task__q"><small>${esc(v.question.label)}</small><span class="task__expr">${esc(v.question.text)}</span></div>` : "";
  const field = v.isAi
    ? `<textarea class="task__solution" id="answer" placeholder="${v.placeholder}" maxlength="1500" aria-describedby="hint"></textarea>`
    : `<input class="task__answer" id="answer" autocomplete="off" inputmode="text" placeholder="${v.placeholder}" maxlength="200" aria-describedby="hint">`;
  stage.innerHTML = `<article class="task">
      <div class="task__meta"><span class="task__num">№${esc(v.number)}</span>${badge}
        <span class="task__pts">${icon("bolt", 15)}+${v.points}</span>
        ${v.solved ? `<span class="task__solved">${icon("check", 15)}розв’язано</span>` : ""}</div>
      <p class="task__cond">${esc(v.condition)}</p>
      ${figs ? `<div class="task__figs">${figs}</div>` : ""}
      ${question}
      ${v.tail ? `<p class="task__tail">${esc(v.tail)}</p>` : ""}
      <label class="visually-hidden" for="answer">${v.isAi ? "Розв’язок" : "Відповідь"}</label>
      ${field}
      <p class="task__hint" id="hint">${v.hint}</p>
    </article>`;
  const input = $("answer");
  input.addEventListener("input", () => {
    input.classList.remove("is-wrong");
    if (state === "answer") mainBtn.disabled = !input.value.trim();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !input.value.trim()) return;
    if (!v.isAi || e.ctrlKey || e.metaKey) { e.preventDefault(); check(); }
  });
  setMain(v.button, "primary", true);
  skipBtn.hidden = false;
  stage.scrollTop = 0;
  input.focus({ preventScroll: true });
}

async function check() {
  const t = tasks[order[pos]], input = $("answer"), text = input.value.trim();
  if (!text || state !== "answer") return;
  const v = taskView(t);
  state = "busy";
  setMain("Перевіряю…", "primary", true);
  const res = v.isAi ? await api.solution(t.exercise.id, text) : await api.check(t.sub.id, text);
  if (!res.ok) {
    const f = errorFeedback(res);
    showFeedback(f);
    if (f.skip) {
      state = "skipping";
      setMain("Далі", "primary");
      skipBtn.hidden = true;
      setTimeout(() => { if (state === "skipping") next(); }, AUTO_SKIP_MS);
      return;
    }
    state = "answer";
    setMain(f.retry ? "Спробувати ще раз" : v.button, "primary");
    return;
  }
  const d = res.data;
  if (d.progress) progress = d.progress;
  updateMe(d);
  const f = feedbackFor(d);
  showFeedback(f);
  if (d.correct) {
    t.solved = true;
    sessionPoints += d.points || 0;
    setProgress();
    state = "next";
    setMain("Далі", "ok");
    skipBtn.hidden = true;
    mainBtn.focus();
  } else {
    input.classList.add("is-wrong");
    if (!reduceMotion()) { input.classList.remove("shake"); void input.offsetWidth; input.classList.add("shake"); }
    state = "answer";
    setMain(v.button, "primary");
    input.focus({ preventScroll: true });
  }
}

function next() { pos += 1; render(); }

// --- Фінал -----------------------------------------------------------------------------

function finish() {
  state = "finish";
  hideFeedback();
  const m = finishModel({ tasks, progress, startStars, sessionPoints, nextUrl });
  const stars = [1, 2, 3].map((i) =>
    `<svg class="icon star ${i <= m.stars ? "star--on" : "star--off"}" style="--i:${i - 1}" width="56" height="56" aria-hidden="true" focusable="false"><use href="#i-star"/></svg>`).join("");
  const burst = m.stars === 3 || m.newStar
    ? `<div class="finish__burst" aria-hidden="true">${Array.from({ length: 14 }, (_, i) => `<i style="--a:${i * 360 / 14}deg;--c:${i % 3}"></i>`).join("")}</div>` : "";
  stage.innerHTML = `<section class="finish" aria-labelledby="finishTitle">
      <div class="finish__stars" role="img" aria-label="${m.starsLabel}">${burst}${stars}</div>
      ${m.newStar ? `<p class="finish__new">${m.newStar}</p>` : ""}
      <h2 class="finish__title" id="finishTitle" tabindex="-1">${m.title}</h2>
      <p class="finish__summary">${m.summary} · <span class="finish__pts">${icon("bolt", 18)}${m.pointsText}</span></p>
    </section>`;
  actions.innerHTML = [
    m.next ? `<a class="btn btn--ok btn--block" href="${esc(nextUrl)}">${icon("play", 18)}Наступний урок</a>` : "",
    `<a class="btn btn--primary btn--block" id="finishMapLink" href="${esc(mapUrl)}">${icon("map", 18)}На мапу</a>`,
    m.retry ? `<button class="btn btn--secondary btn--block" type="button" id="retryBtn">${icon("repeat", 18)}Ще раз — нерозв’язані</button>` : "",
  ].join("");
  $("retryBtn")?.addEventListener("click", retryUnsolved);
  justEarnedStar = Boolean(m.newStar);
  $("finishMapLink")?.addEventListener("click", maybeMarkFinished);
  $("finishTitle").focus({ preventScroll: true });
}

function retryUnsolved() {
  actions.innerHTML = `<button class="btn btn--primary btn--block game__main" id="mainBtn" type="button" disabled>Перевірити</button>
    <button class="btn btn--secondary btn--block" id="skipBtn" type="button">Пропустити</button>`;
  bindButtons();
  order = order.filter((i) => !tasks[i].solved);
  pos = 0;
  render();
}

// --- Порожні стани ---------------------------------------------------------------------

function emptyState(message, { retry = false } = {}) {
  state = "empty";
  stage.innerHTML = `<p class="empty-note game__empty">${esc(message)}</p>`;
  actions.innerHTML = [
    retry ? `<button class="btn btn--primary btn--block" type="button" id="reloadBtn">${icon("repeat", 18)}Спробувати ще раз</button>` : "",
    `<a class="btn btn--${retry ? "secondary" : "primary"} btn--block" href="${esc(mapUrl)}">${icon("map", 18)}На мапу</a>`,
    !retry && theoryUrl ? `<a class="btn btn--secondary btn--block" href="${esc(theoryUrl)}">${icon("book", 18)}Читати теорію</a>` : "",
  ].join("");
  $("reloadBtn")?.addEventListener("click", () => location.reload());
}

// --- Старт -----------------------------------------------------------------------------

function bindButtons() {
  mainBtn = $("mainBtn");
  skipBtn = $("skipBtn");
  mainBtn.addEventListener("click", () => {
    if (state === "answer") check();
    else if (state === "next" || state === "skipping") next();
  });
  skipBtn.addEventListener("click", () => { if (state === "answer" || state === "skipping") next(); });
}

async function start() {
  bindButtons();
  const res = await api.play(kind, lessonId);
  if (!res.ok) {
    if (res.data?.error === "lesson_locked") return emptyState("Цей урок ще закритий — спершу пройди попередній.");
    return emptyState(res.status === 0 ? "Немає зв’язку. Спробуй ще раз." : (res.data?.detail || "Не вдалося завантажити урок."), { retry: true });
  }
  tasks = res.data.tasks || [];
  progress = res.data.progress;
  startStars = progress?.stars ?? 0;
  if (!tasks.length) return emptyState("У цьому уроці ще немає ігрових завдань.");
  order = orderTasks(tasks);
  setProgress();
  render();
}

start();
