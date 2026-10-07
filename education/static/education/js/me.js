// Чіпи гравця у верхній панелі: зірки, бали, серія. Заповнює всі елементи [data-me="…"].
// Інші модулі (гра) оновлюють чіпи без перезавантаження:
//   document.dispatchEvent(new CustomEvent("me:updated", { detail: { points: 60, streak: 5 } }))
import { plural } from "./ui.js";
import { api } from "./api.js";

const DAYS = ["день", "дні", "днів"];

export function fill(me) {
  const set = (key, value) => {
    for (const el of document.querySelectorAll(`[data-me="${key}"]`)) el.textContent = value;
  };
  if ("points" in me) set("points", me.points);
  if ("streak" in me) {
    set("streak", me.streak);
    set("streak_word", plural(me.streak, DAYS));
  }
  if ("stars" in me) set("stars", me.stars);
  if ("max_stars" in me) set("max_stars", me.max_stars);
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
