// Service Worker (фаза 20, беклог FE-0638): офлайн-режим гри — кешує каркас застосунку й дані
// вже відкритого уроку, щоб розірваний зв'язок не стирав екран гри.
//
// Перевірка відповіді (POST /api/play/.../check|solution/) лишається дією, що потребує
// з'єднання: очікувана відповідь ніколи не йде на клієнт (education/api.py — «GET-ендпоінти
// гри ніколи не віддають відповідей»), тож офлайн-перевірка неможлива в принципі без зміни
// цього навмисного рішення. POST-запити цей файл не перехоплює й не кешує.
//
// Версія в назві кешу — єдиний спосіб примусити оновлення (у проєкті нема збирача з хешами
// файлів): зміниш список нижче — зміни й VERSION, інакше старий кеш переживе деплой.
const VERSION = "v4";   // v4 (FE-0644): map-nodes.js — Мудра Сова біля поточного уроку
const SHELL_CACHE = `mw-shell-${VERSION}`;
const RUNTIME_CACHE = `mw-runtime-${VERSION}`;

const SHELL_URLS = [
  "/static/education/css/fonts.css",
  "/static/education/css/tokens.css",
  "/static/education/css/base.css",
  "/static/education/css/components.css",
  "/static/education/css/layout.css",
  "/static/education/css/play.css",
  "/static/education/js/me.js",
  "/static/education/js/play.js",
  "/static/education/js/play-core.js",
  "/static/education/js/map-nodes.js",
  "/static/education/js/sound.js",
  "/static/education/js/api.js",
  "/static/education/js/ui.js",
  "/static/education/fonts/unbounded-cyrillic-500-normal.woff2",
  "/static/education/fonts/unbounded-latin-500-normal.woff2",
  "/static/education/fonts/unbounded-cyrillic-700-normal.woff2",
  "/static/education/fonts/unbounded-latin-700-normal.woff2",
  "/static/education/fonts/nunito-cyrillic-500-normal.woff2",
  "/static/education/fonts/nunito-latin-500-normal.woff2",
  "/static/education/fonts/nunito-cyrillic-600-normal.woff2",
  "/static/education/fonts/nunito-latin-600-normal.woff2",
  "/static/education/fonts/nunito-cyrillic-700-normal.woff2",
  "/static/education/fonts/nunito-latin-700-normal.woff2",
  "/static/education/fonts/nunito-cyrillic-800-normal.woff2",
  "/static/education/fonts/nunito-latin-800-normal.woff2",
  "/static/education/manifest.webmanifest",
  "/static/education/img/favicon.svg",
  "/static/education/img/apple-touch-icon.png",
  "/static/education/img/icon-192.png",
  "/static/education/img/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_URLS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names.filter((n) => n !== SHELL_CACHE && n !== RUNTIME_CACHE).map((n) => caches.delete(n)),
      ))
      .then(() => self.clients.claim()),
  );
});

// Сторінка уроку й дані завдань уроку — єдине, що кешуємо «наживо» (не відповіді, лише умови).
const GAME_PAGE = /^\/play\/(item|paragraph)\/\d+\/$/;
const GAME_API = /^\/api\/play\/(items|paragraphs)\/\d+\/$/;
const isGameUrl = (url) => GAME_PAGE.test(url.pathname) || GAME_API.test(url.pathname);

/** Мережа спершу (свіжий прогрес), кеш — лише запасний варіант, коли мережі нема. */
async function networkFirst(request) {
  try {
    const res = await fetch(request);
    if (res.ok) (await caches.open(RUNTIME_CACHE)).put(request, res.clone());
    return res;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw err;
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;             // перевірка відповіді — POST, не чіпаємо
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (isGameUrl(url)) {
    event.respondWith(networkFirst(request));
  } else if (url.pathname.startsWith("/static/education/")) {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
  }
});
