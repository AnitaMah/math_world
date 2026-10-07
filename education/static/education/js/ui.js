// Дрібні помічники інтерфейсу. ES-модуль: import { plural } from "./ui.js".

/**
 * Українське відмінювання за числом: plural(5, ["день", "дні", "днів"]) → "днів".
 * Форми: [1, 21, 31…], [2–4, 22–24…], [0, 5–20, 25–30…].
 */
export function plural(n, [one, few, many]) {
  const abs = Math.abs(Math.trunc(Number(n) || 0));
  const mod10 = abs % 10, mod100 = abs % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

/** «4 дні», «1 урок», «38 уроків». */
export function count(n, forms) {
  return `${n} ${plural(n, forms)}`;
}
