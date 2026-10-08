// Логіка екрана гри без DOM (фаза 14): порядок завдань, вигляд завдання, відгук, фінал.
// play-v2.js лише малює те, що повертають ці функції. Тести: tools/frontend/tests/play-core.test.mjs.
import { plural } from "./ui.js";

export const DIFFICULTY = {
  preparatory: "Підготовчий", medium: "Середній", sufficient: "Достатній", high: "Високий", olympiad: "Олімпіадний",
};
export const PRAISE = ["Чудово!", "Правильно!", "Так тримати!", "Супер!", "Молодець!"];

export const praise = (rand = Math.random) => PRAISE[Math.floor(rand() * PRAISE.length) % PRAISE.length];

/** Спершу нерозв’язані, потім розв’язані (повторення); всередині — порядок уроку. */
export function orderTasks(tasks) {
  return tasks.map((_, i) => i).sort((a, b) => (tasks[a].solved - tasks[b].solved) || (a - b));
}

export function solvedCount(tasks) {
  return tasks.filter((t) => t.solved).length;
}

export function progressPct(tasks) {
  return tasks.length ? Math.round((100 * solvedCount(tasks)) / tasks.length) : 0;
}

/** Що показати для одного завдання з /api/play/… */
export function taskView(task) {
  const ex = task.exercise || {};
  const isAi = task.kind === "ai";
  return {
    number: ex.number,
    isAi,
    diff: ex.difficulty && DIFFICULTY[ex.difficulty] ? { code: ex.difficulty, name: DIFFICULTY[ex.difficulty] } : null,
    points: task.points || 0,
    solved: Boolean(task.solved),
    condition: ex.condition || "",
    tail: ex.condition_tail || "",
    figures: (ex.figures || []).filter((f) => f.url).map((f) => ({ url: f.url, label: f.number ? `Рис. ${f.number}` : "" })),
    question: task.sub
      ? { label: `Вправа ${ex.number}, ${task.sub.number})`, text: String(task.sub.text || "").replace(/[;.,]\s*$/, "") }
      : null,
    button: isAi ? "Перевірити з ШІ" : "Перевірити",
    placeholder: isAi ? "Напиши розв’язок і відповідь…" : "Твоя відповідь",
    hint: isAi
      ? "Пиши кроки так, як у зошиті. ШІ підкаже, якщо щось не так. Ctrl+Enter — перевірити."
      : "Дріб — через «/», десятковий — через кому: 3/4, 2,5. Так/ні — словом.",
  };
}

/** Відгук на успішну відповідь API перевірки. */
export function feedbackFor(data, rand = Math.random) {
  if (data.correct) {
    return {
      kind: "ok",
      title: praise(rand),
      points: data.points || 0,
      text: data.feedback || (data.already_solved && !data.points ? "Це завдання вже було розв’язано." : ""),
    };
  }
  return {
    kind: "bad",
    title: data.verdict === "unclear" ? "Не зовсім зрозуміло" : "Ще не так",
    points: 0,
    text: data.feedback || "Перевір обчислення і спробуй ще раз.",
  };
}

/** Відгук на помилку запиту. `skip` — завдання пропускаємо автоматично (ШІ недоступний). */
export function errorFeedback(res) {
  const err = res?.data?.error;
  if (res?.status === 503 || err === "ai_unavailable") {
    return { kind: "info", title: "ШІ зараз відпочиває", text: "Цю задачу пропустимо — повернемося до неї пізніше.", skip: true };
  }
  if (!res || res.status === 0 || err === "network") {
    return { kind: "bad", title: "Немає зв’язку", text: "Спробуй ще раз.", retry: true };
  }
  if (res.status === 429) {
    return { kind: "bad", title: "Забагато спроб", text: res.data?.detail || "Зачекай хвилинку і спробуй ще раз." };
  }
  return { kind: "bad", title: "Ой", text: res.data?.detail || "Щось пішло не так, спробуй ще раз.", retry: true };
}

const BALS = ["бал", "бали", "балів"];

/** Екран фіналу уроку. */
export function finishModel({ tasks, progress, startStars = 0, sessionPoints = 0, nextUrl = "" }) {
  const stars = Math.max(0, Math.min(3, progress?.stars ?? 0));
  const done = solvedCount(tasks);
  const total = tasks.length;
  const all = total > 0 && done === total;
  const gained = Math.max(0, stars - startStars);
  return {
    stars,
    starsLabel: `${stars} з 3 зірок`,
    title: all ? "Урок пройдено!" : done ? "Гарна робота!" : "Не здавайся!",
    summary: `Розв’язано ${done} з ${total}`,
    points: sessionPoints,
    pointsText: `+${sessionPoints} ${plural(sessionPoints, BALS)}`,
    newStar: gained === 0 ? "" : gained === 1 ? "Нова зірка!" : "Нові зірки!",
    retry: done < total,
    next: stars === 3 && Boolean(nextUrl),
  };
}
