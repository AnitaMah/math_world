// /ui/tokens/: показує фактичні значення токенів із tokens.css і рахує контраст пар (WCAG 2.1).
const root = getComputedStyle(document.documentElement);
const value = (name) => root.getPropertyValue(name).trim();

for (const el of document.querySelectorAll("[data-token]")) {
  el.textContent = value(el.dataset.token);
}

// Колір у RGB через сам браузер — працює і для hex, і для rgba(), і для var().
const probe = document.createElement("span");
document.body.append(probe);
function rgb(name) {
  probe.style.color = `var(${name})`;
  const m = getComputedStyle(probe).color.match(/[\d.]+/g).map(Number);
  return m.slice(0, 3);
}
const lum = ([r, g, b]) => {
  const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
export function contrast(a, b) {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

for (const row of document.querySelectorAll("tr[data-fg]")) {
  const ratio = contrast(rgb(row.dataset.fg), rgb(row.dataset.bg));
  const cell = row.querySelector(".contrast-ratio");
  const ok = ratio >= Number(row.dataset.min);
  cell.textContent = `${ratio.toFixed(2)}:1 · ${ok ? "OK" : "замало"}`;
  cell.classList.add(ok ? "is-ok" : "is-bad");
}
probe.remove();
