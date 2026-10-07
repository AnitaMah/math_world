// Розкладка архіпелагу (фаза 7): з normalizeMap() → геометрія мапи у координатах viewBox.
// Детерміновано: той самий клас і ті самі уроки → та сама мапа (seed з номера класу й кількості уроків).
//
//   острів  = розділ (blob навколо прямокутника, площа ∝ кількості уроків)
//   ділянка = параграф (менший blob усередині острова, колір .isl-N)
//   вузол   = урок (рівномірно вздовж «змійки» всередині ділянки)
//
// Результат: { width, height, viewBox, islands, regions, routes, connectors, nodes, chips, decor }.

export const DEFAULTS = { width: 1080, height: 820, pad: 20, nodeGap: 72, minGap: 56, corridor: 60, chipBand: 46 };

// --- Випадкові числа з seed (mulberry32) ----------------------------------------------------

export function mulberry32(seed) {
  let a = seed >>> 0;
  return function rnd() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// --- Геометрія -----------------------------------------------------------------------------

const r0 = (v) => Math.round(v);
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

/** Замкнений blob навколо еліпса: n точок з радіусом ±amp, згладжених Catmull-Rom → Безьє. */
export function blob(cx, cy, rx, ry, rnd, n = 10, amp = 0.1) {
  const pts = [];
  for (let i = 0; i < n; i++) {
    const a = (2 * Math.PI * i) / n - Math.PI / 2;
    const k = 1 + (rnd() * 2 - 1) * amp;
    pts.push({ x: cx + rx * k * Math.cos(a), y: cy + ry * k * Math.sin(a) });
  }
  return { d: closedPath(pts), pts };
}

function closedPath(pts) {
  const n = pts.length;
  let d = `M${r0(pts[0].x)},${r0(pts[0].y)}`;
  for (let i = 0; i < n; i++) {
    const p0 = pts[(i - 1 + n) % n], p1 = pts[i], p2 = pts[(i + 1) % n], p3 = pts[(i + 2) % n];
    const c1 = { x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6 };
    const c2 = { x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6 };
    d += ` C${r0(c1.x)},${r0(c1.y)} ${r0(c2.x)},${r0(c2.y)} ${r0(p2.x)},${r0(p2.y)}`;
  }
  return d + "Z";
}

/** Точки на кривій Catmull-Rom через waypoints (steps на сегмент). */
export function spline(wp, steps = 30) {
  if (wp.length === 1) return [{ ...wp[0] }];
  const P = [wp[0], ...wp, wp[wp.length - 1]], out = [];
  for (let i = 1; i < P.length - 2; i++) {
    const [p0, p1, p2, p3] = [P[i - 1], P[i], P[i + 1], P[i + 2]];
    for (let s = 0; s < steps; s++) {
      const t = s / steps, t2 = t * t, t3 = t2 * t;
      const f = (k) => 0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
        + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3);
      out.push({ x: f("x"), y: f("y") });
    }
  }
  out.push({ ...wp[wp.length - 1] });
  return out;
}

function arcLength(pts) {
  let L = 0;
  for (let i = 1; i < pts.length; i++) L += dist(pts[i - 1], pts[i]);
  return L;
}

/** n точок, рівномірно розподілених за довжиною дуги. */
export function sampleEven(pts, n) {
  if (n <= 0) return [];
  if (n === 1) return [pts[Math.floor(pts.length / 2)]];
  const cum = [0];
  for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + dist(pts[i - 1], pts[i]));
  const L = cum[cum.length - 1], res = [];
  let j = 0;
  for (let k = 0; k < n; k++) {
    const t = (L * k) / (n - 1);
    while (j < cum.length - 2 && cum[j + 1] < t) j++;
    const seg = cum[j + 1] - cum[j] || 1, u = (t - cum[j]) / seg;
    res.push({ x: pts[j].x + (pts[j + 1].x - pts[j].x) * u, y: pts[j].y + (pts[j + 1].y - pts[j].y) * u });
  }
  return res;
}

/** Точка всередині многокутника (ray casting). */
export function inside(pt, poly) {
  let ok = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i], b = poly[j];
    if ((a.y > pt.y) !== (b.y > pt.y) && pt.x < ((b.x - a.x) * (pt.y - a.y)) / (b.y - a.y) + a.x) ok = !ok;
  }
  return ok;
}

/** Ламана апроксимація blob (для перевірок «всередині»). */
function polyOf(pts) {
  return spline([...pts, pts[0], pts[1]], 8).slice(4);
}

// --- Розподіл прямокутника пропорційно вагам --------------------------------------------------

/** Ділить відрізок [a, a+len] на частини ∝ weights із проміжками gap. */
function splitLine(a, len, weights, gap) {
  const total = weights.reduce((s, w) => s + w, 0) || 1, free = len - gap * (weights.length - 1);
  let pos = a;
  return weights.map((w) => {
    const size = (free * w) / total, seg = [pos, size];
    pos += size + gap;
    return seg;
  });
}

/** Розбиває масив ваг на rows рядків з приблизно рівними сумами, зберігаючи порядок. */
function partition(weights, rows) {
  const total = weights.reduce((s, w) => s + w, 0), groups = [];
  let cur = [], acc = 0, left = rows;
  weights.forEach((w, i) => {
    cur.push(i);
    acc += w;
    const remaining = weights.length - i - 1;
    if (left > 1 && remaining >= left - 1 && (acc >= total / rows - 1e-9 || remaining === left - 1)) {
      groups.push(cur); cur = []; acc = 0; left--;
    }
  });
  if (cur.length) groups.push(cur);
  return groups;
}

/**
 * Комірки для m частин у прямокутнику: рядки «змійкою» (рядок 0 — зліва направо, 1 — справа наліво…),
 * щоб сусідні частини (параграфи) були поруч. Повертає комірки в порядку частин.
 */
function cells(rect, weights, gap, mirror = false) {
  const m = weights.length;
  if (m === 1) return [{ ...rect, row: 0, rows: 1 }];
  const rows = Math.max(1, Math.min(m, Math.round(Math.sqrt((m * rect.h) / rect.w))));
  const groups = partition(weights, rows);
  const rowW = groups.map((g) => g.reduce((s, i) => s + weights[i], 0));
  const ys = splitLine(rect.y, rect.h, rowW, gap);
  const out = new Array(m);
  groups.forEach((g, r) => {
    // рядок r іде справа наліво, якщо (r непарний) XOR mirror — «змійка» без діагоналей
    const rtl = (r % 2 === 1) !== mirror;
    const seq = rtl ? [...g].reverse() : g;              // порядок зліва направо
    const xs = splitLine(rect.x, rect.w, seq.map((i) => weights[i]), gap);
    seq.forEach((idx, k) => {
      out[idx] = { x: xs[k][0], w: xs[k][1], y: ys[r][0], h: ys[r][1], row: r, rows: groups.length };
    });
  });
  return out;
}

// --- Стежка всередині ділянки ------------------------------------------------------------------

/**
 * Опорні точки «змійки» в еліпсі (cx, cy, rx, ry): lanes смуг уздовж довшої осі.
 * startCorner: 0..3 — з якого кута починати (щоб вхід був ближче до попередньої ділянки).
 */
function snake(cx, cy, rx, ry, lanes, need, startCorner, jitter = []) {
  const horizontal = rx >= ry;
  const [A, B] = horizontal ? [rx, ry] : [ry, rx];   // A — уздовж смуги, B — поперек
  const wp = [];
  for (let l = 0; l < lanes; l++) {
    const t = lanes === 1 ? 0 : -1 + (2 * l) / (lanes - 1);     // -1..1 поперек
    const across = t * B * 0.62;
    const half = A * Math.sqrt(Math.max(0.15, 1 - (across / B) ** 2)) * 0.78;
    const wobble = (jitter[l % (jitter.length || 1)] ?? 0) * B * 0.22;
    const lane = [[-half, across], [0, across + wobble], [half, across]];
    if (l % 2) lane.reverse();
    for (const [along, acr] of lane) wp.push(horizontal ? { x: cx + along, y: cy + acr } : { x: cx + acr, y: cy + along });
  }
  // віддзеркалення під потрібний кут старту
  const flipX = startCorner & 1, flipY = startCorner & 2;
  return wp.map((p) => ({ x: flipX ? 2 * cx - p.x : p.x, y: flipY ? 2 * cy - p.y : p.y }));
}

function routeForRegion(reg, count, prevEnd, nextHint, opts, jitter) {
  if (count === 0) return { pts: [], nodes: [] };
  if (count === 1) return { pts: [], nodes: [{ x: reg.cx, y: reg.cy }] };   // один урок — у центрі, без стежки
  const inner = { rx: Math.max(20, reg.rx - 28), ry: Math.max(20, reg.ry - 28) };
  const need = (count - 1) * opts.nodeGap;
  let best = null;
  const maxLanes = Math.max(1, Math.floor((2 * Math.min(inner.rx, inner.ry) * 0.62 * 2) / 60) + 1);
  for (let lanes = 1; lanes <= Math.max(1, maxLanes); lanes++) {
    for (let corner = 0; corner < 4; corner++) {
      const wp = snake(reg.cx, reg.cy, inner.rx, inner.ry, lanes, need, corner, jitter);
      let curve = spline(wp, 30);
      let L = arcLength(curve);
      if (count > 1 && L < need * 0.95) continue;                // не вміщує уроки — більше смуг
      // задовга стежка для кількох уроків — беремо середню частину потрібної довжини
      if (count > 1 && L > need * 1.6) curve = trimMiddle(curve, need * 1.35);
      const nodes = sampleEven(curve, count);
      const entry = prevEnd ? dist(prevEnd, nodes[0]) : 0;
      const exit = nextHint ? dist(nodes[nodes.length - 1], nextHint) : 0;
      const score = entry + exit + lanes * 40;
      if (!best || score < best.score) best = { score, pts: curve, nodes };
    }
    if (best) break;
  }
  if (!best) {   // зовсім тісно: спіраль-стежка по максимуму смуг
    const wp = snake(reg.cx, reg.cy, inner.rx, inner.ry, Math.max(2, maxLanes + 1), need, 0, jitter);
    const curve = spline(wp, 30);
    best = { pts: curve, nodes: sampleEven(curve, count) };
  }
  return best;
}

function trimMiddle(pts, len) {
  const L = arcLength(pts), from = (L - len) / 2, to = from + len, out = [];
  let acc = 0;
  for (let i = 0; i < pts.length; i++) {
    if (i) acc += dist(pts[i - 1], pts[i]);
    if (acc >= from && acc <= to) out.push(pts[i]);
  }
  return out.length >= 2 ? out : pts;
}

// --- Піктограми суші ---------------------------------------------------------------------------

const ICON_RULES = [
  ["decimal", ["десятков"]],
  ["percent", ["відсот"]],
  ["cube", ["паралелепіпед", "пірамід", "об’єм", "об'єм", "куб", "циліндр", "конус", "куля"]],
  ["triangle", ["кут", "трикутник", "многокутник", "фігур"]],
  ["pie", ["дроб", "коло", "круг", "діаграм", "сектор"]],
  ["ruler", ["відрізок", "відрізк", "шкал", "промін", "координат"]],
  ["equation", ["рівнян", "вираз", "формул"]],
];

/** Піктограма ділянки: спершу назва параграфа, потім назви його уроків (найбільше збігів). */
export function pickIcon(paragraphTitle, lessonTitles = []) {
  const t = String(paragraphTitle).toLowerCase();
  for (const [kind, words] of ICON_RULES) if (words.some((w) => t.includes(w))) return kind;
  const text = lessonTitles.join(" ").toLowerCase();
  let best = null, bestHits = 0;
  for (const [kind, words] of ICON_RULES) {
    const hits = words.reduce((s, w) => s + (text.split(w).length - 1), 0);
    if (hits > bestHits) { best = kind; bestHits = hits; }
  }
  return best;
}

// --- Короткі назви для чіпів ----------------------------------------------------------------

export const CHIP_NAMES = {
  "Додавання і віднімання натуральних чисел": "Додавання і віднімання",
  "Множення і ділення натуральних чисел": "Множення і ділення",
};

export function chipName(shortTitle) {
  if (CHIP_NAMES[shortTitle]) return CHIP_NAMES[shortTitle];
  const words = shortTitle.split(/\s+/);
  if (words.length <= 3) return shortTitle;
  const cut = words.slice(0, 3);
  // не закінчувати сполучником / прийменником
  while (cut.length > 1 && /^(і|й|та|в|у|з|із|до|на|від|за)$/u.test(cut[cut.length - 1])) cut.pop();
  return cut.join(" ");
}

const chipWidth = (text, badge) => 30 + badge.length * 7.5 + text.length * 7.4;

// --- Головна функція ----------------------------------------------------------------------------

const cache = new Map();

export function layoutGrade(map, options = {}) {
  const opts = { ...DEFAULTS, ...options };
  const key = `${map.grade}|${map.lessons.map((l) => `${l.kind}${l.id}:${l.map?.x ?? ""},${l.map?.y ?? ""}`).join(",")}|${JSON.stringify(options)}`;
  if (cache.has(key)) return cache.get(key);

  const seed = (map.grade || 0) * 1000 + map.lessons.length;
  const rnd = options.rnd ?? mulberry32(opts.seed ?? seed);
  const k = map.sections.length;
  const W = opts.width;
  const weightOf = (s) => s.paragraphIdx.reduce((n, p) => n + map.paragraphs[p].lessonIdx.length, 0);
  const avg = map.lessons.length / Math.max(1, k);
  const weights = map.sections.map((s) => Math.max(weightOf(s), 0.6 * avg, 1));

  // 1. Острови: 1–2 — в один ряд; 3+ — рядки по 2 «змійкою», полотно росте вниз
  const perRow = k <= 2 ? k : 2, rowsN = Math.ceil(k / perRow);
  const H = k <= 2 ? opts.height : Math.max(opts.height, rowsN * 400);
  const band = opts.chipBand;
  const area = { x: opts.pad, y: band, w: W - 2 * opts.pad, h: H - 2 * band };
  const rowGroups = [];
  for (let r = 0; r < rowsN; r++) rowGroups.push([...Array(Math.min(perRow, k - r * perRow))].map((_, i) => r * perRow + i));
  const rowYs = splitLine(area.y, area.h, rowGroups.map((g) => g.reduce((s, i) => s + weights[i], 0) || 1), opts.corridor + 2 * band * (rowsN > 1 ? 1 : 0));
  const islandRects = new Array(k), islandRow = new Array(k);
  rowGroups.forEach((g, r) => {
    g.forEach((idx) => { islandRow[idx] = r; });
    const xs = splitLine(area.x, area.w, g.map((i) => weights[i]), opts.corridor);
    const order = r % 2 ? [...xs].reverse() : xs;
    g.forEach((idx, j) => { islandRects[idx] = { x: order[j][0], w: order[j][1], y: rowYs[r][0], h: rowYs[r][1] }; });
  });

  const islands = map.sections.map((s, i) => {
    const R = islandRects[i];
    const b = blob(R.x + R.w / 2, R.y + R.h / 2, (R.w / 2) * 0.96, (R.h / 2) * 0.96, rnd, 12, 0.06);
    return { sectionIdx: i, rect: R, d: b.d, poly: polyOf(b.pts) };
  });

  // 2. Ділянки параграфів у прямокутнику острова. Напрям «змійки» (дзеркало чи ні) для кожного острова
  //    вибираємо так, щоб стежка входила з боку попереднього острова й виходила до наступного —
  //    тоді маршрут човна не перетинає острови.
  const regions = [];
  const center = (c) => ({ x: c.x + c.w / 2, y: c.y + c.h / 2 });
  let prevExit = null;
  map.sections.forEach((s, i) => {
    const R = islandRects[i], inset = 14;
    const inner = { x: R.x + inset, y: R.y + inset, w: R.w - 2 * inset, h: R.h - 2 * inset };
    const pw = s.paragraphIdx.map((p) => Math.max(1, map.paragraphs[p].lessonIdx.length));
    const next = islandRects[i + 1];
    const nextC = next ? center(next) : null;
    let cs = null, bestScore = Infinity;
    for (const mirror of [false, true]) {
      const cand = cells(inner, pw, 10, mirror);
      if (!cand.length) continue;
      const first = center(cand[0]), last = center(cand[cand.length - 1]);
      // перший острів класу: за рівних умов урок 1 — ліворуч угорі (так читають); але маршрут човна,
      // що не перетинає острів, важливіший — тому вага малого «бонусу» лише 0.25
      const entry = prevExit ? dist(prevExit, first) : 0.25 * dist({ x: 0, y: 0 }, first);
      const score = entry + (nextC ? dist(last, nextC) : 0);
      if (score < bestScore - 1) { bestScore = score; cs = cand; }
    }
    cs = cs ?? [];
    if (cs.length) prevExit = center(cs[cs.length - 1]);
    s.paragraphIdx.forEach((p, j) => {
      const c = cs[j];
      const cx = c.x + c.w / 2, cy = c.y + c.h / 2, rx = c.w / 2, ry = c.h / 2;
      const b = blob(cx, cy, rx, ry, rnd, 9, 0.1);
      const jitter = [rnd() * 2 - 1, rnd() * 2 - 1, rnd() * 2 - 1, rnd() * 2 - 1];
      regions.push({ paraIdx: p, sectionIdx: i, isl: map.paragraphs[p].isl, cell: c, cx, cy, rx, ry, d: b.d, jitter });
    });
  });
  regions.sort((a, b) => a.paraIdx - b.paraIdx);

  // 3. Стежки й вузли
  const nodes = new Array(map.lessons.length), routes = [];
  let prevEnd = null;
  regions.forEach((reg, idx) => {
    const lessonIdx = map.paragraphs[reg.paraIdx].lessonIdx;
    const next = regions[idx + 1];
    const nextHint = next ? { x: next.cx, y: next.cy } : null;
    const { pts, nodes: pos } = routeForRegion(reg, lessonIdx.length, prevEnd, nextHint, opts, reg.jitter);
    lessonIdx.forEach((li, j) => {
      const manual = map.lessons[li].map;
      const p = manual && manual.x != null && manual.y != null ? { x: manual.x, y: manual.y } : pos[j];
      nodes[li] = { lessonIdx: li, x: r0(p.x), y: r0(p.y) };
    });
    if (pts.length) {
      const thin = pts.filter((_, i) => i % 3 === 0).concat([pts[pts.length - 1]]);
      routes.push({ paraIdx: reg.paraIdx, d: "M" + thin.map((p) => `${r0(p.x)},${r0(p.y)}`).join(" L") });
    }
    if (lessonIdx.length) prevEnd = nodes[lessonIdx[lessonIdx.length - 1]];
  });

  // 4. З’єднання між параграфами: суша (той самий острів) або човен (між островами)
  const connectors = [];
  for (let i = 0; i + 1 < map.lessons.length; i++) {
    const a = map.lessons[i], b = map.lessons[i + 1];
    if (a.paraIdx === b.paraIdx) continue;
    const p = nodes[i], q = nodes[i + 1];
    if (a.sectionIdx === b.sectionIdx) {
      const mx = (p.x + q.x) / 2, my = (p.y + q.y) / 2;
      connectors.push({ from: i, to: i + 1, kind: "land", d: `M${p.x},${p.y} Q${r0(mx + (q.y - p.y) * 0.15)},${r0(my - (q.x - p.x) * 0.15)} ${q.x},${q.y}` });
    } else {
      const dx = q.x - p.x, dy = q.y - p.y, bend = 0.35;
      const c1 = { x: p.x + dx / 3 - dy * bend, y: p.y + dy / 3 + dx * bend };
      const c2 = { x: p.x + (2 * dx) / 3 + dy * bend, y: p.y + (2 * dy) / 3 - dx * bend };
      const mid = { x: (p.x + 3 * c1.x + 3 * c2.x + q.x) / 8, y: (p.y + 3 * c1.y + 3 * c2.y + q.y) / 8 };
      connectors.push({
        from: i, to: i + 1, kind: "boat",
        d: `M${p.x},${p.y} C${r0(c1.x)},${r0(c1.y)} ${r0(c2.x)},${r0(c2.y)} ${q.x},${q.y}`,
        boat: { x: r0(mid.x), y: r0(mid.y) },
      });
    }
  }

  // 5. Чіпи. Параграфи з ≥ 2 уроками — чіп на параграф (над / під островом, якщо ділянка торкається
  //    краю, інакше над першим вузлом). Розділ, де параграфи по одному уроку (урок = §, Тарасенкова), —
  //    один чіп на острів: 35 чіпів на 35 § не вмістяться і не допоможуть.
  const chips = [], placed = [];
  const place = (chip) => {
    for (const o of placed) {
      if (Math.abs(o.y - chip.y) < chip.h + 4 && chip.x < o.x + o.w + 8 && chip.x + chip.w > o.x - 8) {
        chip.x = Math.min(o.x + o.w + 10, W - chip.w - 4);
      }
    }
    chip.x = r0(chip.x); chip.y = r0(Math.min(Math.max(chip.y, 2), H - chip.h - 2));
    placed.push(chip); chips.push(chip);
  };
  map.sections.forEach((S, si) => {
    const R = islandRects[si];
    const paras = S.paragraphIdx.map((p) => map.paragraphs[p]);
    const perSection = paras.length > 0 && paras.every((P) => P.lessonIdx.length <= 1);
    if (perSection) {
      const text = chipName(S.shortTitle), badge = `Розділ ${S.roman}`, w = chipWidth(text, badge);
      place({ sectionIdx: si, paraIdx: null, x: Math.min(Math.max(R.x + R.w / 2 - w / 2, 4), W - w - 4), y: R.y - 38,
              w: r0(w), h: 28, text, badge, isl: null, where: "top" });
      return;
    }
    regions.filter((reg) => reg.sectionIdx === si).forEach((reg) => {
      const P = map.paragraphs[reg.paraIdx];
      const text = chipName(P.shortTitle), badge = `${S.roman} · §${P.number}`;
      const w = chipWidth(text, badge), h = 28, c = reg.cell;
      let y, where;
      if (c.row === 0) { y = R.y - h - 10; where = "top"; }
      else if (c.row === c.rows - 1) { y = R.y + R.h + 10; where = "bottom"; }
      else { const first = nodes[P.lessonIdx[0]]; y = first ? first.y - 62 : reg.cy - h / 2; where = "inside"; }
      place({ sectionIdx: si, paraIdx: reg.paraIdx, x: Math.min(Math.max(reg.cx - w / 2, 4), W - w - 4), y,
              w: r0(w), h, text, badge, isl: reg.isl, where });
    });
  });

  // 6. Декор: хвилі й цятки у воді, піктограми на суші
  const allPolys = islands.map((i) => i.poly);
  const nodeList = nodes.filter(Boolean);
  const inWater = (pt, margin) => allPolys.every((poly) => !inside(pt, poly))
    && allPolys.every((poly) => poly.every((q) => dist(q, pt) > margin));
  const waves = [], specks = [];
  for (let tries = 0; tries < 400 && (waves.length < 8 || specks.length < 8); tries++) {
    const pt = { x: 10 + rnd() * (W - 60), y: 10 + rnd() * (H - 20) };
    if (!inWater(pt, 30)) continue;
    if (chips.some((c) => pt.x > c.x - 20 && pt.x < c.x + c.w + 20 && pt.y > c.y - 14 && pt.y < c.y + c.h + 14)) continue;
    if (waves.length < 8 && [...waves, ...specks].every((o) => dist(o, pt) > 60)) waves.push({ x: r0(pt.x), y: r0(pt.y) });
    else if (specks.length < 8 && [...waves, ...specks].every((o) => dist(o, pt) > 40)) specks.push({ x: r0(pt.x), y: r0(pt.y), r: 1.2 + r0(rnd() * 4) / 10 });
  }
  const icons = [];
  regions.forEach((reg) => {
    const P = map.paragraphs[reg.paraIdx];
    const kind = pickIcon(P.shortTitle, P.lessonIdx.map((li) => map.lessons[li].title));
    if (!kind) return;
    let best = null, bestD = 0;
    for (let gx = -0.6; gx <= 0.6; gx += 0.15) {
      for (let gy = -0.6; gy <= 0.6; gy += 0.15) {
        if (gx * gx + gy * gy > 0.42) continue;
        const pt = { x: reg.cx + gx * reg.rx, y: reg.cy + gy * reg.ry };
        const d = Math.min(...nodeList.map((n) => dist(n, pt)), Infinity);
        if (d > bestD) { bestD = d; best = pt; }
      }
    }
    if (best && bestD >= 60) icons.push({ paraIdx: reg.paraIdx, kind, x: r0(best.x), y: r0(best.y), isl: reg.isl });
  });

  const result = {
    width: W, height: H, viewBox: `0 0 ${W} ${H}`,
    islands: islands.map(({ poly, ...i }) => i),
    regions: regions.map(({ cell, jitter, ...r }) => ({ ...r, cx: r0(r.cx), cy: r0(r.cy), rx: r0(r.rx), ry: r0(r.ry) })),
    routes, connectors, nodes, chips,
    decor: { waves, specks, icons },
    _polys: allPolys,    // для перевірок «всередині острова»; рендер їх не використовує
  };
  cache.set(key, result);
  return result;
}

// --- Телефон: один параграф вертикально ------------------------------------------------------

/** Один параграф (острів-ділянка) для екрана телефону: вузли «змійкою» згори вниз. */
export function layoutParagraph(map, paraIdx, options = {}) {
  const width = options.width ?? 390, top = options.top ?? 200, step = options.step ?? 76;
  const P = map.paragraphs[paraIdx], n = P.lessonIdx.length;
  const cx = width / 2, amp = Math.min(92, width / 2 - 75);
  const nodes = P.lessonIdx.map((li, i) => ({ lessonIdx: li, x: r0(cx + amp * Math.sin(1.05 * i)), y: r0(top + i * step) }));
  const last = nodes.length ? nodes[nodes.length - 1].y : top;
  const height = last + 220;
  const rnd = mulberry32((map.grade || 0) * 1000 + paraIdx);
  const ry = (last - top) / 2 + 110, cy = (top + last) / 2;
  const island = blob(cx, cy, width / 2 - 26, ry, rnd, 10, 0.06).d;
  const curve = nodes.length > 1 ? spline(nodes.map(({ x, y }) => ({ x, y })), 20) : [];
  const route = curve.length ? "M" + curve.filter((_, i) => i % 3 === 0).concat([curve[curve.length - 1]]).map((p) => `${r0(p.x)},${r0(p.y)}`).join(" L") : "";
  return { width, height, viewBox: `0 0 ${width} ${height}`, island, isl: P.isl, route, nodes };
}
