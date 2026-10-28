// Чіпи гравця у верхній панелі: зірки, бали, серія. Заповнює всі елементи [data-me="…"].
// Інші модулі (гра) оновлюють чіпи без перезавантаження:
//   document.dispatchEvent(new CustomEvent("me:updated", { detail: { points: 60, streak: 5 } }))
import { plural } from "./ui.js";
import { api } from "./api.js";
import { mountTeacherModeToggle } from "./teacher-mode.js";

const DAYS = ["день", "дні", "днів"];
const WEEKDAY_LETTERS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"];

/** Стовпчик за день: висота — бали дня відносно найбільшого дня тижня. */
function renderHistory(container, history) {
  if (!history?.length) return;
  const max = Math.max(1, ...history.map((d) => d.points));
  container.replaceChildren(...history.map((d) => {
    const [y, m, day] = d.date.split("-").map(Number);
    const weekday = WEEKDAY_LETTERS[(new Date(y, m - 1, day).getDay() + 6) % 7];
    const bar = document.createElement("div");
    bar.className = "week-chart__bar";
    bar.style.setProperty("--p", `${Math.round((d.points / max) * 100)}%`);
    const value = document.createElement("span");
    value.className = "week-chart__value";
    value.textContent = d.points;
    const label = document.createElement("span");
    label.className = "week-chart__day";
    label.textContent = weekday;
    bar.append(value, label);
    return bar;
  }));
  const total = history.reduce((s, d) => s + d.points, 0);
  container.setAttribute("aria-label", `Бали за останні 7 днів: усього ${total}`);
}

export function fill(me) {
  const set = (key, value) => {
    for (const el of document.querySelectorAll(`[data-me="${key}"]`)) el.textContent = value;
  };
  if ("points" in me) set("points", me.points);
  if ("streak" in me) {
    set("streak", me.streak);
    set("streak_word", plural(me.streak, DAYS));
    for (const el of document.querySelectorAll("[data-badge]")) {
      el.classList.toggle("badge--earned", me.streak >= Number(el.dataset.badge));
    }
  }
  if ("stars" in me) set("stars", me.stars);
  if ("max_stars" in me) set("max_stars", me.max_stars);
  if ("is_teacher" in me) {
    const toggle = document.getElementById("teacherModeToggle");
    if (toggle) toggle.hidden = !me.is_teacher;
  }
  if ("history" in me) {
    const chart = document.querySelector('[data-me="history"]');
    if (chart) renderHistory(chart, me.history);
  }
}

export async function loadMe() {
  const { ok, data } = await api.me();   // реальний /api/me/ або мок (?mock=1)
  if (!ok) {
    console.warn("[me] не вдалося завантажити дані гравця:", data);
    return null;
  }
  if (!("stars" in data)) {
    console.warn("[me] /api/me/ ще не віддає `stars` (контракт з бекендом) — чіп зірок показує «—».");
  }
  fill(data);
  return data;
}

document.addEventListener("me:updated", (event) => fill(event.detail || {}));
if (document.querySelector("[data-me]")) loadMe();

const teacherModeToggle = document.getElementById("teacherModeToggle");
if (teacherModeToggle) mountTeacherModeToggle(teacherModeToggle);
