// Попередній перегляд розкладки мапи без сервера: node preview_layout.mjs grade-5.json grade-6.json
// Пише SVG у tools/frontend/shots/ (відкрийте в браузері) і друкує перевірки: час, мін. відстань між вузлами,
// вузли поза островом, піктограми.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
mkdirSync(new URL("shots/", import.meta.url), { recursive: true });
import { normalizeMap } from "../../education/static/education/js/api.js";
import { layoutGrade, inside } from "../../education/static/education/js/map-layout.js";
const ACC = ["#4dd0e1","#a28cff","#ffb547","#ff8fa3","#6fdc8c"], LAND = ["#15404a","#2a2658","#40321d","#48233a","#1a4530"];
for (const f of process.argv.slice(2)) {
  const m = normalizeMap(JSON.parse(readFileSync(new URL("../../education/static/education/mock/" + f, import.meta.url), "utf8")));
  const t0 = performance.now(); const L = layoutGrade(m); const ms = performance.now() - t0;
  let minD = 1e9, pair = null;
  for (let i = 0; i < L.nodes.length; i++) for (let j = i + 1; j < L.nodes.length; j++) {
    const d = Math.hypot(L.nodes[i].x - L.nodes[j].x, L.nodes[i].y - L.nodes[j].y); if (d < minD) { minD = d; pair = [i + 1, j + 1]; } }
  const outside = L.nodes.filter((n) => !inside(n, L._polys[m.lessons[n.lessonIdx].sectionIdx])).map((n) => n.lessonIdx + 1);
  console.log(f, `${ms.toFixed(1)}ms`, "size", L.width + "x" + L.height, "minDist", minD.toFixed(1), pair, "outside", outside, "icons", L.decor.icons.map((i) => i.kind).join(","));
  let s = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${L.viewBox}" width="${L.width}" height="${L.height}" style="background:#0b1220;font-family:sans-serif">`;
  for (const w of L.decor.waves) s += `<path d="M${w.x},${w.y} q7,-7 14,0 t14,0 t14,0" fill="none" stroke="#1d2c47" stroke-width="2"/>`;
  for (const p of L.decor.specks) s += `<circle cx="${p.x}" cy="${p.y}" r="${p.r}" fill="#2a3b5c"/>`;
  for (const i of L.islands) s += `<path d="${i.d}" fill="none" stroke="rgba(77,208,225,.07)" stroke-width="26"/><path d="${i.d}" fill="#1f2a3f" stroke="#3a4a68" stroke-width="2"/>`;
  s += `<defs>${L.islands.map((i, k) => `<clipPath id="c${k}"><path d="${i.d}"/></clipPath>`).join("")}</defs>`;
  for (const r of L.regions) s += `<path d="${r.d}" fill="${LAND[r.isl - 1]}" clip-path="url(#c${r.sectionIdx})"/>`;
  for (const ic of L.decor.icons) s += `<text x="${ic.x}" y="${ic.y}" fill="${ACC[ic.isl-1]}" opacity=".6" font-size="14" text-anchor="middle">${ic.kind}</text>`;
  for (const r of L.routes) s += `<path d="${r.d}" fill="none" stroke="rgba(255,255,255,.28)" stroke-width="3" stroke-dasharray="1 9" stroke-linecap="round"/>`;
  for (const c of L.connectors) s += `<path d="${c.d}" fill="none" stroke="${c.kind === "boat" ? "rgba(159,231,240,.55)" : "rgba(255,255,255,.28)"}" stroke-width="2.5" stroke-dasharray="${c.kind === "boat" ? "6 7" : "1 9"}" stroke-linecap="round"/>` + (c.boat ? `<circle cx="${c.boat.x}" cy="${c.boat.y}" r="8" fill="#c9a26b"/>` : "");
  for (const n of L.nodes) { const l = m.lessons[n.lessonIdx]; const a = ACC[m.paragraphs[l.paraIdx].isl - 1];
    s += `<circle cx="${n.x}" cy="${n.y}" r="23" fill="${l.state === "soon" ? "#121826" : a}" stroke="${l.state === "current" ? "#fff" : a}" stroke-width="3"/><text x="${n.x}" y="${n.y + 5}" text-anchor="middle" font-size="14" font-weight="700" fill="${l.state === "soon" ? "#7782a0" : "#0d1220"}">${l.number}</text>`; }
  for (const c of L.chips) s += `<rect x="${c.x}" y="${c.y}" width="${c.w}" height="${c.h}" rx="14" fill="#0e1626" stroke="#263149"/><text x="${c.x + 10}" y="${c.y + 19}" font-size="13" font-weight="700" fill="#eef1f6">${c.badge}  ${c.text}</text>`;
  writeFileSync(new URL(`shots/layout-${f.replace(".json", "")}.svg`, import.meta.url), s + "</svg>");
}
