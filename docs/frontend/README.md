# Фронтенд «Математичного світу»

Мапа-архіпелаг: клас = архіпелаг, розділ = острів, параграф = ділянка острова свого кольору, урок = вузол
на стежці. Дизайн — полотно «Математичний світ — мапа» (`docs/frontend/design/`), план робіт —
`PLAN.md`, усі рішення й причини — `DECISIONS.md`.

**Стек**: Django-шаблони + ванільний JS (ES-модулі) + CSS. Без збірки: файли з `static/` віддаються як є.
Node потрібен лише для тестів (`tools/frontend/`).

## Швидкий старт

```bash
python manage.py runserver
# http://127.0.0.1:8000/            — «Світ» (вибір класу)
# http://127.0.0.1:8000/grades/5/   — мапа 5 класу
# http://127.0.0.1:8000/ui/kit/     — UI-кіт (лише DEBUG)
```

Тести фронтенду однією командою (Windows теж):

```bash
cd tools/frontend && npm ci && npx playwright install chromium && cd ../..   # один раз
python tools/frontend/run_tests.py             # JS + Django UI + моки + візуальні
python tools/frontend/run_tests.py --no-visual # швидко, без браузера
```

На Linux/CI те саме — `make frontend-test` / `make frontend-unit` / `make frontend-baseline`.

## Структура

| Де | Що |
|---|---|
| `education/views_ui.py` | тонкі view нового UI: «Світ», мапа, урок, сторінка §, гра, «Прогрес», «Профіль», службові `/ui/…` |
| `education/views.py` | точки входу за старими іменами URL, 301-редиректи зі старих адрес, реєстрація, `_blocks_context` |
| `education/templatetags/ui.py` | `{% icon %}`, `{% topbar %}`, `{% auth_field %}`, фільтри `uk_plural`, `block_name`, `block_icon`, `difficulty_name`, `reflow` |
| `education/context.py` | `UI_DEBUG` → `<html data-debug="1">` (моки лише в DEBUG) |
| `templates/education/base.html` | каркас: шрифти, токени, спрайт іконок, верхня панель, нижня навігація |
| `templates/education/` | `world`, `map`, `lesson`, `progress`, `profile` (+ `_lesson_blocks`), `play`, `ui_*`; фрагменти `_topbar`, `_bottom_nav`, `_icons`, `_stars`, `_progress` |
| `templates/registration/` | вхід і реєстрація (`_auth_base`, `_field`) |
| `templates/404.html`, `500.html` | сторінки помилок (500 — статичний HTML без тегів) |

### CSS (`static/education/css/`)

| Файл | Що |
|---|---|
| `tokens.css` | **усі кольори** (+ розміри, відступи, радіуси, рух). Інші файли кольорів не мають — це перевіряє тест |
| `fonts.css` | Unbounded 500/700, Nunito 500–800 (свої woff2, кирилиця + латиниця) |
| `base.css` | скидання, фокус, `.visually-hidden`, `prefers-reduced-motion`, іконки |
| `components.css` | кнопки, чіпи, теги, статуси, картки, прогрес, зірки, бейдж складності `.diff` |
| `layout.css` | верхня панель, нижня навігація, сторінки-заглушки, 404 |
| `map.css`, `world.css`, `lesson.css`, `play.css`, `auth.css` | екрани |
| `ui-dev.css` | лише для `/ui/tokens/` і `/ui/kit/` |

Колір острова — клас `.isl-1…5` на предку: він задає `--acc` і `--land`. Параграф N класу → `isl-((N-1) % 5 + 1)`.

### JS (`static/education/js/`)

| Модуль | Що | Тести (`tools/frontend/tests/`) |
|---|---|---|
| `api.js` | єдиний клієнт API, моки, `normalizeMap()` | `api.test.mjs` |
| `map-layout.js` | геометрія мапи (детермінована) | `map-layout.test.mjs` |
| `map-nodes.js` | вузли уроків, «блукаючий» tabindex, ярлик «Ти тут» | `map-nodes.test.mjs` |
| `lesson-panel.js` | модель і рендер панелі уроку, текстова альтернатива мапи | `lesson-panel.test.mjs` |
| `map-mobile.js` | телефон: одна група за раз, свайпи, нижній лист | `map-mobile.test.mjs` |
| `map.js` | сторінка мапи: море, острови, підписи, зв’язок усіх частин | — (знімки) |
| `world.js` | картки класів з мініатюрами | `world.test.mjs` |
| `play-core.js` / `play.js` | гра: логіка без DOM / малювання | `play-core.test.mjs` |
| `me.js` | чіпи гравця (`[data-me]`, подія `me:updated`) | — |
| `ui.js` | `plural()`, `count()` — українське відмінювання | `ui.test.mjs` |

Правило: **логіка — в чистих функціях без DOM** (їх тестує `node --test`), DOM — тонкий шар поверх.

## Як додати новий екран

1. View у `views_ui.py` (тонкий: дані → `render`), URL у `math_world/urls.py`.
2. Шаблон `{% extends "education/base.html" %}`; блоки `title`, `body_class`, `styles`, `content`, `scripts`.
   Повноекранний екран — порожні `{% block topbar %}{% endblock %}` і `{% block bottom_nav %}{% endblock %}`.
3. Стилі — новий файл у `css/`, **лише `var(--…)`** з `tokens.css`. Потрібен новий колір — спершу токен.
4. Іконки — `{% icon "назва" size=20 %}`; нова — `<symbol id="i-назва">` у `_icons.html` + ім’я в `ICONS`.
5. Логіку JS — у чисту функцію з тестом у `tools/frontend/tests/`.
6. Знімок — додай екран у `tools/frontend/visual.spec.js` і `python tools/frontend/run_tests.py --baseline`.
7. Перевір клавіатуру й axe (див. DECISIONS, фаза 16), запиши рішення в `DECISIONS.md`.

## Компоненти

Живий каталог — **`/ui/kit/`** (і токени — `/ui/tokens/`), лише при DEBUG.

| Компонент | Клас / тег | Де в кіті |
|---|---|---|
| Кнопки | `.btn` + `--primary`, `--secondary`, `--ok`, `--bad`, `--info`, `--muted`, `--sm`, `--block`; `.btn-icon` 44×44 | «Кнопки» |
| Чіпи, теги, статуси | `.chip`, `.tag`, `.status--done/current/open/locked`, `.sec-chip` | «Чіпи, теги, статуси» |
| Картки | `.card`, `--dashed`, `--float`; `.empty-note` | «Картки, прогрес, зірки» |
| Прогрес | `{% include "education/_progress.html" with value= max= label= size= %}` | там само |
| Зірки | `{% include "education/_stars.html" with count= size= outline= %}` | там само |
| Рядки панелі | `.feature-row`, `.score-row` | «Рядки панелі уроку» |
| Бейдж складності | `.diff .diff--preparatory…olympiad` | (теорія, гра) |
| Поле форми | `{% auth_field field %}` → `.field` | (вхід) |
| Розкладка | `.stack`, `.row` (+ `--gap-N`, `--between`) | «Розкладка» |
| Іконки | `{% icon "star" size=18 label="…" %}` — 22 символи | «Іконки» |

## Мапа: як додати новий клас

Нічого малювати не треба: мапу будує `map-layout.js` з `/api/grades/<n>/map/`.

1. Імпортуй підручник (бекенд) — у класу з’являться розділи, параграфи, уроки.
2. Вкладка класу у верхній панелі й картка у «Світі» з’являються самі (з БД). Колонка «у тумані» —
   наступний номер після найстаршого класу.
3. `layoutGrade()` робить: острів на розділ (площа ∝ кількості уроків, ряди по 2–3), усередині — ділянки
   параграфів, у ділянці — «змійка» з рівним кроком між вузлами; між параграфами — суходіл, між
   островами — човен. Розкладка **детермінована** (seed = номер класу + кількість уроків): та сама мапа
   при кожному відкритті. Підписи островів — `CHIP_NAMES` (короткі назви довгих розділів), іконки ділянок —
   `ICON_RULES` (за словами в назві: «десятков» → 0,5, «паралелепіпед» → куб…).
4. Клас, де урок = § (Тарасенкова, без пунктів), працює сам: `normalizeMap` робить § уроком `kind:"paragraph"`.
5. **Поправити вузол вручну**: заповни `Item.map_x/map_y` (або `Paragraph.map_x/map_y` для §-уроку) у
   координатах viewBox мапи (за замовчуванням 1080×820; подивитись координати — `/ui/api/` або
   `node tools/frontend/preview_layout.mjs`). API віддає їх як `map {x, y}`, вузол стане туди; стежка
   ділянки лишається автоматичною.
6. Перевір на телефоні (≤ 720 px): там мапа показує одну групу за раз (параграф, або розділ, якщо урок = §).

## Моки

Моки = **контракт з бекендом** (`static/education/mock/`, формат — `mock/README.md`). Фронтенд можна
розробляти без бекенду:

| Адреса | Що |
|---|---|
| `/grades/5/?mock=1` | мапа з мок-даних |
| `?mock=demo` | прогрес «посередині»: пройдені, поточний, закриті, у хмарах |
| `?mock=states` | усі стани вузлів поруч |
| `?mock_user=1` | залогінений гравець |
| `/play/item/<id>/?mock=1` | гра на моках (відповіді 13, 81, 6; ШІ — розв’язок з 16 і 9); `&mock_ai=off`, `&mock_play=empty` |

Моки працюють **лише при DEBUG** (`<html data-debug="1">`). `localStorage.mw_mock = "demo"` — те саме без `?mock`.

**Змінився контракт** →
1. онови моки: `python tools/frontend/make_mocks.py` (мапи) або вручну (`play.json`, `me.*.json`);
2. `python tools/frontend/check_mocks.py` — моки відповідають схемі;
3. `python tools/frontend/diff_contract.py --base http://127.0.0.1:8000` — форма реальних відповідей
   збігається з моками (код 1 — є розбіжності; контракт головний, назви полів виправляє бекенд);
4. якщо змінився вигляд — `python tools/frontend/run_tests.py --baseline` і перевір нові еталони очима.

## Візуальні тести

`tools/frontend/visual.spec.js`: 6 екранів (світ, мапа, урок, гра, фінал, вхід) × 1440 і 390 px, допуск
1 % пікселів, без анімацій (`reducedMotion`). Дані — моки + окрема демо-база `tools/frontend/ui.sqlite3`
(`seed_ui.py`; робоча `db.sqlite3` не змінюється — без `DB_PATH` скрипт відмовляється працювати).

Еталони — `docs/frontend/baseline/*-{desktop|mobile}-{linux|win32}.png`, окремо для кожної ОС (шрифти
рендеряться по-різному). Локально відсутній еталон створюється сам; у CI — помилка.

- Навмисно змінив дизайн → `run_tests.py --baseline`, переглянь нові PNG, закоміть.
- Оновив `@playwright/test` або еталони Linux розійшлися з CI → запусти workflow **frontend** вручну з
  `update_baselines` і забери артефакт `frontend-baselines`.
- Впав тест → у CI артефакт `playwright-report` (знімок, очікуване, різниця).

## CI

`.github/workflows/frontend.yml`, job `frontend`: Python 3.13 + Node 22, `npm ci`, кеш браузерів
Playwright за версією, `python tools/frontend/run_tests.py`. Запускається на зміни в `education/`,
`math_world/`, `tools/frontend/`, `docs/frontend/baseline/`.
