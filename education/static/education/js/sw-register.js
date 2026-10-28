// Реєстрація Service Worker (фаза 20, беклог FE-0638) — одна на весь застосунок: урок
// кешується, щойно гравець його відкриє, ще до того, як зникне зв'язок.
if ("serviceWorker" in navigator) {
  globalThis.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((err) => {
      console.warn("[sw] не вдалося зареєструвати service worker:", err);
    });
  });
}
