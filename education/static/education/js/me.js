// Чіпи гравця у верхній панелі: зірки, бали, серія. Заповнює всі елементи [data-me="…"].
// Інші модулі (гра) оновлюють чіпи без перезавантаження:
//   document.dispatchEvent(new CustomEvent("me:updated", { detail: { points: 60, streak: 5 } }))
import { plural } from "./ui.js";

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
  // TODO(FE-фаза-6): брати через js/api.js (моки/реальний API), а не fetch напряму
  try {
    const response = await fetch("/api/me/", { credentials: "same-origin" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const me = await response.json();
    if (!("stars" in me)) {
      console.warn("[me] /api/me/ ще не віддає `stars` (контракт з бекендом) — чіп зірок показує «—».");
    }
    fill(me);
    return me;
  } catch (error) {
    console.warn("[me] не вдалося завантажити /api/me/:", error);
    return null;
  }
}

document.addEventListener("me:updated", (event) => fill(event.detail || {}));
if (document.querySelector("[data-me]")) loadMe();
