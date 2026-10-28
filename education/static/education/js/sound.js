// Звуки правильної/неправильної відповіді, з вимикачем (фаза 20, беклог FE-0637).
// Синтезовані Web Audio API — без аудіофайлів (жодного збирача в проєкті, зайвий асет).

const KEY = "mw_sound";

/** Увімкнено за замовчуванням, поки гравець явно не вимкнув. */
export function isSoundOn() {
  try {
    return globalThis.localStorage?.getItem(KEY) !== "0";
  } catch {
    return true;   // приватне вікно, заблоковане сховище
  }
}

export function setSoundOn(on) {
  try {
    globalThis.localStorage?.setItem(KEY, on ? "1" : "0");
  } catch {
    /* приватне вікно — перемикач діє лише в цій вкладці */
  }
}

let ctx;
/** AudioContext створюємо лише тут, у відповідь на дію гравця (click → check()) — не на
    завантаженні сторінки, інакше браузер попереджає про автозапуск без жесту. */
function audioCtx() {
  if (ctx === undefined) {
    const Ctor = globalThis.AudioContext ?? globalThis.webkitAudioContext;
    ctx = Ctor ? new Ctor() : null;
  }
  return ctx;
}

/** Одна нота: синус, що швидко наростає й плавно згасає (без клацання на межах). */
function tone(ac, freq, start, dur, peak) {
  const osc = ac.createOscillator();
  const gain = ac.createGain();
  osc.type = "sine";
  osc.frequency.value = freq;
  const t0 = ac.currentTime + start;
  gain.gain.setValueAtTime(0, t0);
  gain.gain.linearRampToValueAtTime(peak, t0 + 0.015);
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(gain).connect(ac.destination);
  osc.start(t0);
  osc.stop(t0 + dur + 0.02);
}

/** "ok" — дві висхідні ноти; "bad" — дві низхідні, нижче й коротше. Мовчить, якщо звук вимкнено. */
export function playFeedbackSound(kind) {
  if (!isSoundOn() || (kind !== "ok" && kind !== "bad")) return;
  const ac = audioCtx();
  if (!ac) return;
  if (ac.state === "suspended") ac.resume();
  if (kind === "ok") {
    tone(ac, 659.25, 0, 0.12, 0.16);     // E5
    tone(ac, 987.77, 0.1, 0.18, 0.16);   // B5
  } else {
    tone(ac, 220, 0, 0.16, 0.13);        // A3
    tone(ac, 174.61, 0.1, 0.22, 0.13);   // F3
  }
}

/** Підключає кнопку-вимикач: клік перемикає стан, оновлює aria-pressed, іконку й підпис. */
export function mountSoundToggle(btn) {
  const sync = () => {
    const on = isSoundOn();
    btn.setAttribute("aria-pressed", String(on));
    const use = btn.querySelector("use");
    if (use) use.setAttribute("href", on ? "#i-sound-on" : "#i-sound-off");
    const label = btn.querySelector("[data-sound-label]");
    if (label) label.textContent = on ? "Увімкнено" : "Вимкнено";
    btn.setAttribute("aria-label", on ? "Звук увімкнено, вимкнути" : "Звук вимкнено, увімкнути");
  };
  btn.addEventListener("click", () => {
    setSoundOn(!isSoundOn());
    sync();
  });
  sync();
}
