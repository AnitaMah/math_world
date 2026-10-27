// Тести чистих функцій js/map-pan.js (node:test): масштабування й панорамування мапи (фаза 20, FE-0634).
import { test } from "node:test";
import assert from "node:assert/strict";
import { zoomAt, panBy, clampState, visibleRect } from "../../../education/static/education/js/map-pan.js";

const bounds = (over = { contentWidth: 1000, contentHeight: 800, viewportWidth: 1000, viewportHeight: 800 }) =>
  ({ min: 1, max: 3, ...over });

test("clampState: за межами в'юпорта контент не випускає порожню смугу", () => {
  // точне прилягання (scale 1) — панорамувати нікуди, завжди (0,0)
  assert.deepEqual(clampState({ scale: 1, tx: 40, ty: -40 }, bounds()), { scale: 1, tx: 0, ty: 0 });
  // збільшено вдвічі — контент 2000×1600 у в'юпорті 1000×800, можна зсунути на [-1000, 0]
  const z = clampState({ scale: 2, tx: 50, ty: -2000 }, bounds());
  assert.deepEqual(z, { scale: 2, tx: 0, ty: -800 });
});

test("panBy: зсуває на (dx, dy) і клампить", () => {
  const b = bounds();
  const s0 = { scale: 2, tx: -100, ty: -50 };
  assert.deepEqual(panBy(s0, 10, -5, b), { scale: 2, tx: -90, ty: -55 });
  assert.deepEqual(panBy(s0, 999, 999, b), { scale: 2, tx: 0, ty: 0 });        // впирається в край
  assert.deepEqual(panBy(s0, -999, -999, b), { scale: 2, tx: -1000, ty: -800 });
});

test("zoomAt: межі масштабу (min/max) і точка під курсором лишається на місці", () => {
  const b = bounds();
  const s0 = { scale: 1, tx: 0, ty: 0 };
  const z = zoomAt(s0, 2, 500, 400, b);             // зум ×2 у центрі в'юпорта
  assert.equal(z.scale, 2);
  // точка під курсором (500,400) мала лишитись там же: (originX - px*scale) === originX, бо px = origin/1
  assert.deepEqual(z, { scale: 2, tx: -500, ty: -400 });
  // не можна перевищити max
  const capped = zoomAt(z, 10, 500, 400, b);
  assert.equal(capped.scale, 3);
  // не можна опуститись нижче min
  const back = zoomAt(capped, 0.01, 500, 400, b);
  assert.deepEqual(back, { scale: 1, tx: 0, ty: 0 });
});

test("zoomAt: зум у довільній точці (не в центрі) рахує px/py відносно поточного стану", () => {
  const b = bounds();
  const s0 = { scale: 1, tx: 0, ty: 0 };
  const z = zoomAt(s0, 1.5, 100, 100, b);
  // px = (100-0)/1 = 100; новий tx = 100 - 100*1.5 = -50
  assert.deepEqual(z, { scale: 1.5, tx: -50, ty: -50 });
});

test("visibleRect: без зуму видно все полотно (для рамки мінімапи, фаза 20, FE-0635)", () => {
  assert.deepEqual(visibleRect({ scale: 1, tx: 0, ty: 0 }, bounds()), { x: 0, y: 0, w: 1, h: 1 });
});

test("visibleRect: зум ×2 у центрі — видно середню чверть полотна", () => {
  assert.deepEqual(visibleRect({ scale: 2, tx: -500, ty: -400 }, bounds()), { x: 0.25, y: 0.25, w: 0.5, h: 0.5 });
});

test("visibleRect: зум ×2 без зсуву — видно верхній лівий кут", () => {
  assert.deepEqual(visibleRect({ scale: 2, tx: 0, ty: 0 }, bounds()), { x: 0, y: 0, w: 0.5, h: 0.5 });
});
