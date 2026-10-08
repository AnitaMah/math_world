// Єдиний клієнт API для всіх екранів нового UI (фаза 6).
// Режим моків (фронтенд без нового бекенду): ?mock=1 | demo | states у URL сторінки
// або localStorage.mw_mock = "1". ?mock_user=1 — залогінений гравець у моках.
// Формат відповідей = контракт із бекендом (static/education/mock/README.md).

const MOCK_BASE = new URL("../mock/", import.meta.url);

// --- HTTP ---------------------------------------------------------------------------

export async function getJSON(url) {
  try {
    const response = await fetch(url, { credentials: "same-origin" });
    const data = await response.json().catch(() => ({ error: "bad_response", detail: "Сервер відповів незрозуміло" }));
    return { ok: response.ok, status: response.status, data };
  } catch (error) {
    return { ok: false, status: 0, data: { error: "network", detail: "Немає зв’язку. Спробуй ще раз" } };
  }
}

function csrfToken() {
  return globalThis.document?.querySelector("[name=csrfmiddlewaretoken]")?.value ?? "";
}

export async function postJSON(url, body) {
  try {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({ error: "bad_response", detail: "Сервер відповів незрозуміло" }));
    return { ok: response.ok, status: response.status, data };
  } catch (error) {
    return { ok: false, status: 0, data: { error: "network", detail: "Немає зв’язку. Спробуй ще раз" } };
  }
}

// --- Режим моків ----------------------------------------------------------------------

/** "" (реальний API) | "1" | "demo" | "states". */
export function mockMode(search = globalThis.location?.search ?? "") {
  const fromUrl = new URLSearchParams(search).get("mock");
  if (fromUrl !== null) return fromUrl === "0" ? "" : (fromUrl || "1");
  try {
    return globalThis.localStorage?.getItem("mw_mock") || "";
  } catch {
    return "";   // приватне вікно, заблоковане сховище
  }
}

function mockUser(search = globalThis.location?.search ?? "") {
  return new URLSearchParams(search).get("mock_user") === "1";
}

const mockFile = (name) => getJSON(new URL(name, MOCK_BASE).href);

// --- Ендпоінти --------------------------------------------------------------------------

export const api = {
  me() {
    return mockMode() ? mockFile(mockUser() ? "me.user.json" : "me.guest.json") : getJSON("/api/me/");
  },
  grades() {
    return mockMode() ? mockFile("grades.json") : getJSON("/api/grades/");
  },
  gradeMap(n) {
    const mode = mockMode();
    if (!mode) return getJSON(`/api/grades/${n}/map/`);
    const variant = n === 5 && (mode === "demo" || mode === "states") ? `.${mode}` : "";
    return mockFile(`grade-${n}${variant}.json`);
  },
  play(kind, id) {
    if (mockMode()) return mockFile(new URLSearchParams(globalThis.location?.search ?? "").get("mock_play") === "empty" ? "play.empty.json" : "play.json");
    return getJSON(`/api/play/${kind === "paragraph" ? "paragraphs" : "items"}/${id}/`);
  },
  check(subId, answer) {
    if (mockMode()) return mockCheck(subId, answer);
    return postJSON(`/api/subexercises/${subId}/check/`, { answer });
  },
  solution(exId, solution) {
    if (mockMode()) return mockSolution(exId, solution);
    return postJSON(`/api/exercises/${exId}/solution/`, { solution });
  },
};

// --- Моки перевірки (лише ?mock=…; правильні відповіді — у play.json._mock_answers) ------

let mockPoints = 40;

async function mockCheck(subId, answer) {
  const { data } = await mockFile("play.json");
  const correct = String(data._mock_answers?.[subId] ?? "").replace(",", ".") === String(answer).trim().replace(",", ".");
  const task = data.tasks.find((t) => t.sub?.id === subId);
  const points = correct ? task?.points ?? 1 : 0;
  mockPoints += points;
  return { ok: true, status: 200, data: { subexercise: subId, correct, points, already_solved: false,
    total_points: mockPoints, streak: 3, progress: { solved: 2, total: 4, points: 7, stars: correct ? 2 : 1 } } };
}

async function mockSolution(exId, solution) {
  if (new URLSearchParams(globalThis.location?.search ?? "").get("mock_ai") === "off") {
    return { ok: false, status: 503, data: { error: "ai_unavailable", detail: "Перевірка ШІ не налаштована" } };
  }
  const correct = /16/.test(solution) && /9/.test(solution);
  mockPoints += correct ? 5 : 0;
  return { ok: true, status: 200, data: { exercise: exId, correct, verdict: correct ? "correct" : "wrong",
    feedback: correct ? "Усе вірно: MK = 16 см, KN = 9 см." : "Склади рівняння: x + (x + 7) = 25.",
    points: correct ? 5 : 0, already_solved: false, total_points: mockPoints, streak: 3,
    progress: { solved: 4, total: 4, points: 12, stars: correct ? 3 : 2 } } };
}

// --- Фолбеки, поки бекенд не віддає всіх полів контракту -------------------------------

/** Стан уроку, якщо в відповіді немає `state`. `locked` фронтенд не вигадує — це правило бекенду. */
export function deriveState(lesson, current) {
  if (lesson.state) return lesson.state;
  const total = lesson.total ?? lesson.exercises ?? 0;
  if (!total) return "soon";
  if (current && current.id === lesson.id && (current.kind ?? "item") === (lesson.kind ?? "item")) return "current";
  if ((lesson.stars ?? 0) > 0) return "done";
  return "open";
}

/** Завдання уроку; старий API віддає лише `exercises` — тоді приблизно, з позначкою approx. */
export function deriveTasks(lesson) {
  if (lesson.tasks) return { auto: lesson.tasks.auto ?? 0, ai: lesson.tasks.ai ?? 0, approx: false };
  return { auto: lesson.exercises ?? 0, ai: 0, approx: true };
}

const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
export function roman(n) {
  return ROMAN[n] ?? String(n);
}

/** «§ 1. Натуральні числа» → «Натуральні числа»; «Розділ I. Натуральні…» → «Натуральні…». */
export function stripNumber(title) {
  return String(title ?? "").replace(/^\s*(§\s*\d+|Розділ\s+[IVX\d]+)\.?\s*/u, "").trim();
}

/**
 * Відповідь /api/grades/<n>/map/ → плаский вигляд для мапи:
 * { grade, textbook, current, sections[], paragraphs[], lessons[] }.
 * Урок Тарасенкової (параграф без items) стає одним уроком kind:"paragraph".
 */
export function normalizeMap(raw) {
  const sections = [], paragraphs = [], lessons = [];
  const current = raw.current ?? null;
  (raw.sections ?? []).forEach((s, sectionIdx) => {
    const section = { id: s.id, number: s.number, roman: roman(s.number), title: s.title,
                      shortTitle: stripNumber(s.title), paragraphIdx: [] };
    sections.push(section);
    (s.paragraphs ?? []).forEach((p) => {
      const paraIdx = paragraphs.length;
      const paragraph = { id: p.id, number: p.number, title: p.title, shortTitle: stripNumber(p.title),
                          sectionIdx, isl: (paraIdx % 5) + 1, lessonIdx: [] };
      paragraphs.push(paragraph);
      section.paragraphIdx.push(paraIdx);
      const items = p.items?.length ? p.items.map((it) => ({ ...it, kind: "item" })) : [{ ...p, kind: "paragraph" }];
      for (const it of items) {
        const tasks = deriveTasks(it);
        const total = it.total ?? (tasks.auto + tasks.ai);
        const lesson = {
          id: it.id, kind: it.kind, number: it.number, title: it.title, sectionIdx, paraIdx,
          stars: it.stars ?? 0, solved: it.solved ?? 0, total, tasks, blocks: it.blocks ?? [],
          map: it.map ?? { x: null, y: null },
        };
        lesson.state = deriveState({ ...it, total }, current);
        paragraph.lessonIdx.push(lessons.length);
        lessons.push(lesson);
      }
    });
  });
  return { grade: raw.grade, subject: raw.subject, textbook: raw.textbook ?? null, current, sections, paragraphs, lessons };
}
