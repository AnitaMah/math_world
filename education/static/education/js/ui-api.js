// /ui/api/ (лише DEBUG): показує відповіді api.* і результат normalizeMap() — для перевірки контракту.
import { api, mockMode, normalizeMap } from "./api.js";

const out = document.getElementById("out");
document.getElementById("mode").textContent = mockMode() ? `моки (${mockMode()})` : "реальний API";

function block(title, ok, body) {
  const section = document.createElement("section");
  section.className = "card stack stack--gap-2";
  const h = document.createElement("h2");
  h.className = "label-caps";
  h.textContent = `${title} — ${ok ? "OK" : "помилка"}`;
  const pre = document.createElement("pre");
  pre.className = "ui-dev__pre";
  pre.textContent = typeof body === "string" ? body : JSON.stringify(body, null, 2);
  section.append(h, pre);
  return section;
}

const summary = (m) => ({
  grade: m.grade, sections: m.sections.length, paragraphs: m.paragraphs.length, lessons: m.lessons.length,
  states: m.lessons.reduce((acc, l) => ({ ...acc, [l.state]: (acc[l.state] ?? 0) + 1 }), {}),
  current: m.current, firstLessons: m.lessons.slice(0, 7),
});

(async () => {
  out.replaceChildren();
  const me = await api.me();
  out.append(block("api.me()", me.ok, me.data));
  const grades = await api.grades();
  out.append(block("api.grades()", grades.ok, grades.data));
  for (const n of [5, 6]) {
    const res = await api.gradeMap(n);
    out.append(block(`normalizeMap(api.gradeMap(${n}))`, res.ok, res.ok ? summary(normalizeMap(res.data)) : res.data));
  }
})();
