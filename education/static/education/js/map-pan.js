// Масштабування й панорамування мапи на десктопі (фаза 20, беклог FE-0634): колесо + перетягування,
// корисно для великих класів (> 50 уроків). Телефон має свій окремий однопараграфний вигляд — не чіпаємо.
// Трансформуємо #mapCanvas (SVG + HTML-вузли разом), transform-origin лишаємо 0 0 — математика нижче
// вважає tx/ty зсувом від лівого верхнього кута.

const clampAxis = (t, content, viewport) => (content <= viewport ? 0 : Math.min(0, Math.max(viewport - content, t)));

/** Утримує точку (originX, originY) у в’юпорті нерухомою під час зміни масштабу. */
export function zoomAt(state, factor, originX, originY, bounds) {
  const scale = Math.min(bounds.max, Math.max(bounds.min, state.scale * factor));
  const px = (originX - state.tx) / state.scale;
  const py = (originY - state.ty) / state.scale;
  return clampState({ scale, tx: originX - px * scale, ty: originY - py * scale }, bounds);
}

/** Зсуває полотно на (dx, dy) екранних пікселів, не випускаючи його за межі в’юпорта. */
export function panBy(state, dx, dy, bounds) {
  return clampState({ ...state, tx: state.tx + dx, ty: state.ty + dy }, bounds);
}

/** Не дає відсунути контент так, щоб лишилась порожня смуга з краю (і не займається, поки не збільшено). */
export function clampState(state, bounds) {
  const w = bounds.contentWidth * state.scale, h = bounds.contentHeight * state.scale;
  return { scale: state.scale, tx: clampAxis(state.tx, w, bounds.viewportWidth), ty: clampAxis(state.ty, h, bounds.viewportHeight) };
}

/** Підключає колесо (зум до курсора), перетягування мишею й подвійний клік (зум/скидання) до stage. */
export function mountPanZoom(stage, canvas, { min = 1, max = 3 } = {}) {
  let state = { scale: min, tx: 0, ty: 0 };
  let drag = null;

  const bounds = () => ({
    min, max, contentWidth: canvas.clientWidth, contentHeight: canvas.clientHeight,
    viewportWidth: stage.clientWidth, viewportHeight: stage.clientHeight,
  });
  const apply = () => {
    canvas.style.transform = `translate(${state.tx}px, ${state.ty}px) scale(${state.scale})`;
    stage.classList.toggle("is-zoomed", state.scale > min);
  };
  const reset = () => { state = { scale: min, tx: 0, ty: 0 }; apply(); };

  stage.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = stage.getBoundingClientRect();
    state = zoomAt(state, Math.exp(-e.deltaY * 0.0015), e.clientX - rect.left, e.clientY - rect.top, bounds());
    apply();
  }, { passive: false });

  stage.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || state.scale <= min || e.target.closest(".node")) return;
    drag = { x: e.clientX, y: e.clientY, tx: state.tx, ty: state.ty };
    stage.setPointerCapture(e.pointerId);
    stage.classList.add("is-panning");
    e.preventDefault();
  });
  stage.addEventListener("pointermove", (e) => {
    if (!drag) return;
    state = panBy({ ...state, tx: drag.tx, ty: drag.ty }, e.clientX - drag.x, e.clientY - drag.y, bounds());
    apply();
  });
  const endDrag = () => { drag = null; stage.classList.remove("is-panning"); };
  stage.addEventListener("pointerup", endDrag);
  stage.addEventListener("pointercancel", endDrag);

  stage.addEventListener("dblclick", (e) => {
    if (e.target.closest(".node")) return;     // вузол сам веде в гру подвійним кліком
    if (state.scale > min) return reset();
    const rect = stage.getBoundingClientRect();
    state = zoomAt(state, max / min, e.clientX - rect.left, e.clientY - rect.top, bounds());
    apply();
  });

  new ResizeObserver(() => { state = clampState(state, bounds()); apply(); }).observe(stage);

  return { reset };
}
