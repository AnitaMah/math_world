// Екран гри: тягне завдання уроку з /api/play/..., показує по одному, перевіряє через API.
(() => {
  const root = document.getElementById("play");
  const $ = (id) => document.getElementById(id);
  const stage = $("stage"), mainBtn = $("mainBtn"), skipBtn = $("skipBtn");
  const fb = $("feedback"), fbIcon = $("feedbackIcon"), fbTitle = $("feedbackTitle"), fbText = $("feedbackText");
  const csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
  const DIFF = {preparatory: "Підготовчий", medium: "Середній", sufficient: "Достатній", high: "Високий", olympiad: "Олімпіадний"};
  const PRAISE = ["Чудово!", "Правильно!", "Так тримати!", "Супер!", "Молодець!"];

  let tasks = [], order = [], pos = 0, state = "answer", sessionPoints = 0, progress = null;

  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

  async function api(url, body) {
    const opts = body ? {method: "POST", headers: {"Content-Type": "application/json", "X-CSRFToken": csrf},
                         body: JSON.stringify(body), credentials: "same-origin"} : {credentials: "same-origin"};
    const r = await fetch(url, opts);
    const data = await r.json().catch(() => ({error: "bad_response", detail: "Сервер відповів незрозуміло"}));
    return {ok: r.ok, status: r.status, data};
  }

  function setProgress() {
    const done = tasks.filter((t) => t.solved).length;
    const pct = tasks.length ? Math.round(100 * done / tasks.length) : 0;
    $("progressFill").style.width = pct + "%";
    document.querySelector(".play-progress").setAttribute("aria-valuenow", pct);
  }

  function showFeedback(kind, title, text) {
    fb.hidden = false;
    fb.className = "feedback feedback--" + kind;
    fbIcon.textContent = kind === "ok" ? "✓" : "✗";
    fbTitle.textContent = title;
    fbText.textContent = text || "";
  }

  function hideFeedback() { fb.hidden = true; }

  function render() {
    hideFeedback();
    state = "answer";
    if (pos >= order.length) return finish();
    const t = tasks[order[pos]], ex = t.exercise;
    const badge = t.kind === "ai" ? '<span class="badge badge--ai">ШІ перевірить</span>'
      : (ex.difficulty ? `<span class="badge badge--${ex.difficulty}">${DIFF[ex.difficulty] || ""}</span>` : "");
    const figs = ex.figures.filter((f) => f.url).map((f) => `<figure class="task-figure"><img src="${f.url}" alt="Рисунок ${esc(f.number)}"></figure>`).join("");
    const question = t.sub
      ? `<div class="task-question"><small>Вправа ${ex.number}, ${esc(t.sub.number)})</small>${esc(t.sub.text.replace(/[;.]$/, ""))}</div>`
      : "";
    const input = t.kind === "ai"
      ? `<textarea class="solution-input" id="answer" placeholder="Напиши розв'язок і відповідь…" maxlength="1500"></textarea>
         <p class="hint">Пиши кроки так, як у зошиті. ШІ підкаже, якщо щось не так.</p>`
      : `<input class="answer-input" id="answer" autocomplete="off" inputmode="text" placeholder="Твоя відповідь" maxlength="200">
         <p class="hint">Дріб — через «/», десятковий — через кому: 3/4, 2,5. Так/ні — словом.</p>`;
    stage.innerHTML = `<div class="task-meta"><span>№${ex.number}</span>${badge}<span>+${t.points} ⭐</span>${t.solved ? "<span>✓ розв'язано</span>" : ""}</div>
      <p class="task-condition">${esc(ex.condition)}</p>${figs}${question}${input}`;
    const field = $("answer");
    field.addEventListener("input", () => { mainBtn.disabled = !field.value.trim(); });
    field.addEventListener("keydown", (e) => { if (e.key === "Enter" && t.kind !== "ai" && field.value.trim()) check(); });
    mainBtn.textContent = t.kind === "ai" ? "Перевірити з ШІ" : "Перевірити";
    mainBtn.className = "btn btn--primary";
    mainBtn.disabled = true;
    skipBtn.hidden = false;
    field.focus({preventScroll: true});
  }

  async function check() {
    const t = tasks[order[pos]], field = $("answer"), text = field.value.trim();
    if (!text || state !== "answer") return;
    state = "busy"; mainBtn.disabled = true; mainBtn.textContent = "Перевіряю…";
    const res = t.kind === "ai"
      ? await api(`/api/exercises/${t.exercise.id}/solution/`, {solution: text})
      : await api(`/api/subexercises/${t.sub.id}/check/`, {answer: text});
    if (!res.ok) {
      state = "answer"; mainBtn.disabled = false; mainBtn.textContent = "Перевірити";
      return showFeedback("bad", "Ой", res.data.detail || "Помилка, спробуй ще раз");
    }
    const d = res.data;
    if (d.progress) progress = d.progress;
    if (d.total_points !== undefined) $("points").textContent = d.total_points;
    if (d.streak !== undefined) $("streak").textContent = d.streak;
    if (d.correct) {
      t.solved = true; sessionPoints += d.points || 0; setProgress();
      const pts = d.points ? ` +${d.points} ⭐` : (d.already_solved ? " (вже було розв'язано)" : "");
      showFeedback("ok", PRAISE[Math.floor(Math.random() * PRAISE.length)] + pts, d.feedback || "");
      state = "next"; mainBtn.textContent = "Далі"; mainBtn.className = "btn btn--ok"; mainBtn.disabled = false;
      skipBtn.hidden = true;
    } else {
      field.classList.remove("shake"); void field.offsetWidth; field.classList.add("shake");
      showFeedback("bad", d.verdict === "unclear" ? "Не зовсім зрозуміло" : "Ще не так",
                   d.feedback || "Перевір обчислення і спробуй ще раз.");
      state = "answer"; mainBtn.textContent = t.kind === "ai" ? "Перевірити з ШІ" : "Перевірити";
      mainBtn.className = "btn btn--bad"; mainBtn.disabled = false;
    }
  }

  function next() { pos += 1; render(); }

  function finish() {
    const stars = progress ? progress.stars : 0;
    const starHtml = [1, 2, 3].map((i) => `<span class="${i <= stars ? "" : "off"}">★</span>`).join("");
    const done = tasks.filter((t) => t.solved).length;
    stage.innerHTML = `<div class="finish"><div class="finish-stars" aria-label="${stars} з 3 зірок">${starHtml}</div>
      <h2>${done === tasks.length ? "Урок пройдено!" : "Гарна робота!"}</h2>
      <p>Розв'язано ${done} з ${tasks.length} · за цей раз +${sessionPoints} ⭐</p></div>`;
    hideFeedback();
    mainBtn.className = "btn btn--primary"; mainBtn.disabled = false;
    mainBtn.textContent = done === tasks.length ? "До уроку" : "Ще раз — нерозв'язані";
    state = done === tasks.length ? "exit" : "again";
    skipBtn.hidden = true;
  }

  mainBtn.addEventListener("click", () => {
    if (state === "answer") check();
    else if (state === "next") next();
    else if (state === "exit") location.href = root.dataset.back;
    else if (state === "again") { order = order.filter((i) => !tasks[i].solved); pos = 0; render(); }
  });
  skipBtn.addEventListener("click", () => { if (state === "answer") next(); });

  (async () => {
    const [play, me] = await Promise.all([api(root.dataset.api), api("/api/me/")]);
    if (me.ok) { $("points").textContent = me.data.points; $("streak").textContent = me.data.streak; }
    if (!play.ok) { stage.innerHTML = `<p class="empty">${esc(play.data.detail || "Не вдалося завантажити урок")}</p>`; return; }
    tasks = play.data.tasks; progress = play.data.progress;
    document.title = play.data.lesson.title + " · гра";
    if (!tasks.length) {
      stage.innerHTML = '<p class="empty">У цьому уроці ще немає ігрових завдань.</p>';
      mainBtn.textContent = "До уроку"; mainBtn.disabled = false; state = "exit"; skipBtn.hidden = true; return;
    }
    // Спершу нерозв'язані, потім розв'язані (повторення)
    order = tasks.map((_, i) => i).sort((a, b) => tasks[a].solved - tasks[b].solved);
    setProgress(); render();
  })();
})();
