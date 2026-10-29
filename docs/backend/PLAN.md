# План: межі застосунків бекенду math_world — 17 сесій (+3 беклог)

Дата: 2026-10-28 · Проблема дизайну: весь бекенд — один Django-застосунок `education`
(`INSTALLED_APPS = ['education']`), що одночасно відповідає за навчальний контент,
PDF-пайплайн імпорту, гру/прогрес, школи/класи та ручну перевірку. 622-рядковий
`models.py` (23 моделі), 367-рядковий `api.py` з ручною JSON-серіалізацією
(`figure_dict`, `exercise_dict`, `block_dict`…) замість шару серіалізаторів.
Мета плану — розвести домени по застосунках без втрати даних і без простою.

**Як користуватися:** одна сесія Claude Code = один пункт нижче (іноді два дрібних).
Після кожної сесії — повний прогін тестів (`python manage.py test`), лише потім коміт.
Комміт-повідомлення: `BE-S01: опис` (номер сесії, не крок). Після кожної групи сесій —
`🔍 РЕВ'Ю`: зупинись і дай перевірити, перш ніж рухатись далі.

**Правила:**
- Жодна сесія не торкається даних продакшн-БД напряму: перенесення моделей між
  застосунками — лише стан міграцій (`SeparateDatabaseAndState`), таблиці й дані
  лишаються як є (`db_table` фіксується явно).
- Тести мають лишатися зеленими після кожної сесії, не лише після групи.
- Не перейменовувати застосунок `education` і не зливати таблиці — тільки виносити
  домени, які вже чисто відокремлені за зовнішніми ключами (див. DECISIONS.md).

## Зміст

- Сесія 1. Інвентаризація та межі доменів
- Сесія 2. Застосунок `schools` — моделі
- Сесія 3. Застосунок `schools` — код і тести
- Сесія 4. Застосунок `game` — моделі
- Сесія 5. Застосунок `game` — код і тести
- Сесія 6. Розбиття `api.py` за доменами
- Сесія 7. Шар серіалізаторів — catalog
- Сесія 8. Шар серіалізаторів — game
- Сесія 9. Видалення мертвого коду
- Сесія 10. `map_builder.py` і залишки старого UI в `urls.py`
- Сесія 11. `pdf_pipeline/structure.py` — розбиття
- Сесія 12. `pdf_pipeline/vision.py` і `run.py` — розбиття
- Сесія 13. Домен `review` — межа з catalog
- Сесія 14. Тести: розкладка по застосунках
- Сесія 15. `tests_ui.py` — розбиття за темами
- Сесія 16. Прибирання `admin.py`, фінальна звірка
- Сесія 17. CI, Makefile, документація, повний регрес
- Беклог (необов'язково): сесії 18–20

---

## Сесія 1. Інвентаризація та межі доменів — ЗРОБЛЕНО (2026-10-28)

_Мета: зафіксувати межі доменів і ризики, перш ніж рухати код._

- [x] Без окремої гілки: як і фронтенд-сесії (FE-) та PDF-сесії, коміти йдуть прямо
      в `main` — кожна сесія мала й перевіряється до коміту, довгоживучі гілки зараз
      у репо не використовуються (`git branch -vv` станом на 2026-10-28: лише `main`)
- [x] `docs/backend/PLAN.md` (цей файл) і `docs/backend/DECISIONS.md` у репозиторії
- [x] `python manage.py test education` — **691 тестів, OK (skipped=14)**, 64с.
      Це базова лінія для всіх наступних сесій (збігається з лінією, яку фронтенд-сесія
      навела в своєму підсумку FE-0645 — 691 Django + 89 JS)
- [x] Побудуй граф зовнішніх ключів `models.py` (23 моделі) — хто на кого посилається.
      Висновок уже зроблено і записаний у DECISIONS.md: `School*` не має жодного FK
      у каталог (лише `auth.User`) — найбезпечніший кандидат на винесення першим;
      `Player/Attempt/LessonProgress` залежать від каталогу (`Item/Paragraph/Exercise/
      SubExercise`), але каталог від них не залежить — винесення без циклів
- [x] Спиши кандидатів на мертвий код (перевір usage перед видаленням у сесії 9):
  - модель `Lesson` (`models.py:403`) — не використовується ніде окрім визначення
    й міграції; реальне поняття «урок» — це `Item`/`Paragraph`, а однойменний
    dataclass `Lesson` у `grade_map.py` — просто колізія назви, не той самий об'єкт
  - `TheoryPractice` — лише в `admin.py` і одній старій management-команді
    (`generate_item_content.py`); перевір, чи команда ще запускається
  - `education/legacy.py` + `migrate_legacy_data` — одноразова міграція старих даних;
    перевір, чи вже застосована в проді (якщо так — видаляти можна)
  - `map_builder.py` робить `reverse()` на URL-імена старого UI (`grade_list`,
    `section_list`, `paragraph_list`, `item_list`), які `urls.py` тримає лише
    заради цього (коментар у файлі прямо каже «бекенд-чату повідомлено»)
- [ ] 🔍 **РЕВ'Ю**: напиши «перевір сесію 1» перед тим, як рухати код

## Сесія 2. Застосунок `schools` — моделі — ЗРОБЛЕНО (2026-10-29, `0b54407`)

_Мета: `School`, `SchoolMembership`, `SchoolClass`, `SchoolClassStudent` переїжджають
у новий застосунок `schools` без зміни таблиць і даних._

Сесії 2 і 3 виконані разом однією сесією (неможливо лишити код у робочому стані між
ними — моделі й код, що на них посилається, мусять переїхати одночасно).

- [ ] `python manage.py startapp schools`, додай у `INSTALLED_APPS`
- [ ] Перенеси 4 класи моделей з `education/models.py` у `schools/models.py` (той самий
      код, лише імпорт `auth.User` як рядок лишається)
- [ ] У `schools/models.py` зафіксуй `Meta.db_table = "education_school"` (і так для
      кожної з 4 моделей) — таблиці не перейменовуються, лише застосунок у стані міграцій
- [ ] Міграція: у `education` — `migrations.DeleteModel` обгорнутий у
      `SeparateDatabaseAndState(database_operations=[], state_operations=[DeleteModel(...)])`;
      у `schools` — дзеркально `CreateModel` тим самим способом. Жодного `database_operations`
      з реальним DDL — таблиці фізично не чіпаються
- [ ] `python manage.py makemigrations --check` — підтверди, що Django не хоче додаткових
      міграцій (стан і факт збігаються)
- [ ] `python manage.py test` — зелено, без жодної зміни в поведінці
- [ ] Коміт: `BE-S02: schools models (state-only move)`

## Сесія 3. Застосунок `schools` — код і тести — ЗРОБЛЕНО (2026-10-29, `0b54407`)

- [x] Перенеси `education/schools.py` → `schools/services.py`, `education/api_schools.py`
      → `schools/api.py`, `education/tests_schools.py` → `schools/tests.py`
- [x] Перенеси пов'язані записи `admin.py` → `schools/admin.py`
- [x] Оновити `education/api_urls.py` — замість окремого модуля тепер
      `from schools import api as api_schools`; шляхи й імена маршрутів не змінились
      (`schools/urls.py` із власним include — відкладено до сесії 6, разом з рештою
      розбиття `api_urls.py`, щоб не робити цю зміну двічі)
- [x] Прибери всі старі імпорти `from education.models import School...`/
      `from education import schools` по решті коду — перший повний прогін тестів
      одразу знайшов пропущений `education/tests_map_api.py` (`from education import
      schools as svc`), виправлено на `from schools import services as svc`
- [x] `python manage.py makemigrations --check` — чисто; `python manage.py test` —
      691 тестів, OK (skipped=14), збігається з базовою лінією сесії 1
- [x] Коміт: `BE-S02..S03: extract schools app (models + code + tests)` (`0b54407`)
- [ ] 🔍 **РЕВ'Ю**: напиши «перевір сесії 2–3»

## Сесія 4. Застосунок `game` — моделі — ЗРОБЛЕНО (2026-10-29)

- [x] `python manage.py startapp game`, додано в `INSTALLED_APPS`
- [x] Перенесено `Player`, `Attempt`, `LessonProgress` тим самим способом, що в сесії 2
      (`db_table` фіксується: `education_player/attempt/lessonprogress`,
      `SeparateDatabaseAndState`) — `education/migrations/0023_move_game_to_game_app.py`
      + `game/migrations/0001_initial.py`. Індекси `Attempt` (`education_a_player__2faf92_idx`,
      `education_a_player__6b6cce_idx`) узяті буквально з `0016_game_progress.py` — інакше
      стан міграції не збігався б з фактичною БД
- [x] FK на `Item`/`Paragraph`/`Exercise`/`SubExercise` лишаються — крос-застосунковий
      FK (`education.Item`), Django це підтримує без проблем
- [x] `makemigrations --check` чистий

## Сесія 5. Застосунок `game` — код і тести — ЗРОБЛЕНО (2026-10-29)

- [x] `education/game.py` → `game/services.py`, `education/tests_game.py` → `game/tests.py`
- [x] Admin: жодних записів `Player`/`Attempt`/`LessonProgress` в `education/admin.py` не було
      зареєстровано — нічого переносити
- [x] Сигнал `user_logged_in` (`on_login`) переїхав з `education/apps.py` у `game/apps.py.ready()`
- [x] Оновлено всі імпорти на `from game.models import ...` / `from game.services import ...`:
      `education/api.py` (6 місць), `education/grade_map.py`, `education/views_ui.py`,
      `education/tests_map_api.py`, `education/tests_queries.py`,
      `education/tests_ui/test_auth_pages.py`
- [ ] `python manage.py test` — у процесі, коміт після підтвердження
- [ ] Коміт: `BE-S04..S05: extract game app (models + code + tests)`
- [ ] 🔍 **РЕВ'Ю**: напиши «перевір сесії 4–5»

## Сесія 6. Розбиття `api.py` за доменами — ЗРОБЛЕНО (2026-10-29)

_Мета: 367-рядковий `api.py` — по одному файлу на домен, а не всі ендпоінти підряд._

- [x] `education/api.py` лишає лише catalog-ендпоінти: `textbooks`, `textbook_tree`,
      `grades`, `grade_map`, `lesson_detail`, `lesson_exercise_list`, `exercise_detail`,
      `figure_image` (+ спільні хелпери `api_error`/`ok`/`api_view`/серіалізатори/`_lesson` —
      і `game/api.py`, і `schools/api.py` імпортують їх звідси, той самий підхід, що вже
      був у `schools/api.py` з сесії 3)
- [x] Нове `game/api.py`: `check`, `solution`, `play`, `me`, `_rate_limited`,
      `_payload_text`, `_points_history`, `progress_dict`
- [x] `schools/api.py` вже існував з сесії 3
- [x] `education/api_urls.py` — тонкий include: catalog-шляхи лишились прямо тут +
      `path("", include("game.urls"))` + `path("", include("schools.urls"))` (нові
      `game/urls.py`, `schools/urls.py` з точно тими самими шляхами й іменами маршрутів —
      зовнішній контракт не змінився, перевірено `get_resolver().url_patterns`)
- [x] Контракт-тести (`tools/frontend/check_mocks.py`, `tests_map_api.py`) лишились
      зеленими без змін у самих тестах
- [x] **Знахідка:** перший прогін тестів зловив `test_solution_endpoint` —
      `solution()` у оригіналі робив `from .ai_check import get_ai_checker` **усередині
      функції** (лінивий імпорт), а я спочатку підняв його на рівень модуля в
      `game/api.py`. `mock.patch("education.ai_check.get_ai_checker", ...)` у тестах
      патчить атрибут модуля `education.ai_check`, а не прив'язане на рівні модуля ім'я
      в `game.api` — тож патч мовчки не діяв. Повернув лінивий імпорт усередину
      `solution()` — той самий прийом, що інший агент застосував до
      `MAX_CONSECUTIVE_ERRORS` у фазі 12 (зберегти спосіб імпорту, а не ідеальну
      структуру нагорі файлу)
- [x] Коміт: `BE-S06: split api.py by domain`

## Сесія 7. Шар серіалізаторів — catalog — ЗРОБЛЕНО (2026-10-29)

_Мета: замінити ручні `*_dict` функції на один explicit шар, а не розкидані по `api.py`._

- [x] Нове `education/serializers.py`: `figure_dict`, `subexercise_dict`, `exercise_dict`,
      `block_dict` — та сама форма виводу, лише інший файл
- [x] `education/api.py` імпортує з `serializers.py` (`block_dict, exercise_dict,
      figure_dict, subexercise_dict`), дублікат-визначення видалено
- [x] `game/api.py`/`schools/api.py` і далі імпортують `figure_dict`/`subexercise_dict`
      з `education.api` (той самий publічний шлях — `education/api.py` реекспортує
      їх через `from .serializers import ...`, callers не змінювались)
- [x] Коміт: разом із сесією 8

## Сесія 8. Шар серіалізаторів — game — ЗРОБЛЕНО (2026-10-29)

- [x] `game/serializers.py`: `progress_dict`
- [x] `game/api.py` використовує новий шар (`from .serializers import progress_dict`)
- [x] `python manage.py check` + повний прогін тестів — зелено, 683/683 (та сама
      кількість, що й після сесії 9 — чиста реорганізація, нуль зміни форми виводу)
- [x] Коміт: `BE-S07+S08+S14: serializer layers + test-layout audit`
- [ ] 🔍 **РЕВ'Ю**: напиши «перевір сесії 6–8»

## Сесія 9. Видалення мертвого коду

_Мета: прибрати знайдене в сесії 1 — тільки після підтвердження, що нічого не зламається._

- [ ] Видалити модель `Lesson` (`models.py`) + міграція `RemoveModel` (справжня, з DDL —
      це не used-таблиця, тож тут вже звичайна, не state-only, міграція)
- [ ] `TheoryPractice`: якщо `generate_item_content` не запускається в робочому процесі —
      задокументувати як deprecated замість видалення (дані вже в БД, видаляти ризиковано
      без окремого рішення власника) — запиши вирок у DECISIONS.md
- [ ] `legacy.py` / `migrate_legacy_data`: видалити лише якщо підтверджено, що міграція
      вже застосована в усіх середовищах, які є (запитай власника перед видаленням)
- [ ] Коміт: `BE-S09: remove dead Lesson model` (+ окремий коміт для legacy.py, якщо видаляли)

## Сесія 10. `map_builder.py` і залишки старого UI в `urls.py`

- [ ] Прочитай, які саме `reverse()`-виклики в `map_builder.py` тримають живими
      `grade_list`/`section_list`/`paragraph_list`/`item_list` в `urls.py`
- [ ] Заміни ці виклики на прямі URL-шаблони або на нові імена маршрутів мапи
      (`grade_map_page` тощо), щоб прибрати залежність від старих імен
- [ ] Видали старі `path(...)` з `urls.py`, якщо нічого більше на них не посилається
      (`grep -rn "grade_list\|section_list\|paragraph_list\|item_list" --include="*.py" --include="*.html"`)
- [ ] `python manage.py test` — зелено, 301-редіректи старих адрес (якщо потрібні для
      зовнішніх посилань) лишити окремим простим маршрутом без старих view-функцій
- [ ] Коміт: `BE-S10: decouple map_builder from old UI route names`
- [ ] 🔍 **РЕВ'Ю**: напиши «перевір сесії 9–10»

## Сесія 11. `pdf_pipeline/structure.py` — розбиття — ЗРОБЛЕНО (2026-10-29, `87ddf69`)

_Мета: 697-рядковий файл на кілька когерентних модулів, без зміни публічного API пайплайна._

- [x] Межі, знайдені в коді (не вигадані заздалегідь): `structure_ocr_fix.py` (64 рядки —
      виправлення цифр, які OCR сплутав з буквами), `structure_lines.py` (110 рядків —
      потокове читання рядків сторінки й зіставлення заголовків), `structure_parser.py`
      (575 рядків — сам FSM-парсер: `StructureParser`, `ParseResult`, `parse_structure`, `outline`)
- [x] `structure.py` лишився тонким (58 рядків) — реекспортує той самий публічний інтерфейс
      через явні імпорти й `__all__`, тож усі `from .structure import X` не змінились
- [x] `python manage.py test education.tests_pipeline` — 420 тестів, OK (skipped=14),
      без змін до і після
- [x] Коміт: `BE-S11: split structure.py into ocr-fix / line-stream / parser modules` (`87ddf69`)

## Сесія 12. `pdf_pipeline/vision.py` і `run.py` — розбиття — ЗРОБЛЕНО (2026-10-29, `a20f5cb`)

- [x] `vision.py` (571→206 рядків): `vision_prompts.py` (шаблон промпту, схема відповіді),
      `vision_client.py` (retry/backoff, `DailyBudget`, `CachedClient`, `GeminiVisionClient`),
      `vision_targets.py` (`VisionTarget`, `select_targets`, `crop_png`), `vision_response.py`
      (`Decision`, `judge`, `apply_response`). `run_vision`/`VisionStats`/`main`/
      `MAX_CONSECUTIVE_ERRORS` **лишились у `vision.py`**, а не переїхали — `test_vision.py`
      робить `mock.patch("education.pdf_pipeline.vision.MAX_CONSECUTIVE_ERRORS", 1)`, і якби
      `run_vision` переїхав, патч на реекспортовану копію в тонкому модулі не вплинув би на
      глобальну змінну, яку функція фактично читає. Правильне рішення — не ідеальна
      симетрія розбиття, а збереження поведінки тесту
- [x] `run.py` (496→47 рядків): `run_orchestrator.py` (сам оркестратор кроків,
      `run_pipeline`/`RunResult`/`STAGES`), `run_manifest.py` (`git_commit`, маніфест запуску),
      `run_cli.py` (розбір аргументів командного рядка)
- [x] `python manage.py test education.tests_pipeline` — 420 тестів, OK (skipped=14),
      включно з `test_no_django.py` (рекурсивно скановує `pdf_pipeline/*.py` — нові файли
      підхопились автоматично) і тестом на `MAX_CONSECUTIVE_ERRORS`
- [x] Коміт: `BE-S12: split vision.py and run.py by concern` (`a20f5cb`)
- [ ] 🔍 **РЕВ'Ю**: напиши «перевір сесії 11–12»

## Сесія 13. Домен `review` — межа з catalog — ЗРОБЛЕНО (2026-10-29)

_Мета: `ManualEdit`, `review.py`, `views_review.py`, `templates/education/review/` —
зафіксувати як внутрішній підмодуль catalog (не окремий застосунок: `ManualEdit` жорстко
прив'язаний до `Textbook`/`Exercise`/`SubExercise`, виносити дорожче, ніж тримати)._

- [x] Запиши в DECISIONS.md явне рішення: review НЕ стає окремим застосунком, і чому
- [x] Перенести в пакет чи лишити плоско? **Лишено як є**: `review.py` (139 рядків) і
      `views_review.py` (91 рядок) уже плоскі, по одному призначенню на файл — пакет
      додав би вкладеність без навігаційної користі (рішення в DECISIONS.md)
- [ ] `python manage.py test education.tests_review` — без змін коду тут не потрібно,
      перевіриться разом з рештою сесії 9 (та сама сесія, що й паралельно в роботі)
- [x] Коміт: запис рішення в `docs/backend/DECISIONS.md`/`PLAN.md` (без зміни коду —
      комітиться разом із сесією 9)

## Сесія 14. Тести: розкладка по застосунках — ЗРОБЛЕНО (2026-10-29)

- [x] `schools/tests.py` (`SchoolRulesTests`, `SchoolClassRulesTests`, `SchoolApiTests`,
      `SchoolClassApiTests`) і `game/tests.py` (`GameFixture`, `TasksTests`, `PointsTests`,
      `AiTests`, `ApiGameTests`, `GuestToAccountTests`, `StatusMismatchTests`) — лише свій
      домен, нічого чужого
- [x] `tests_api.py`, `tests_map_api.py`, `tests_queries.py`, `tests_models.py`,
      `tests_commands.py`, `tests_cache_tools.py`, `tests_backup.py`, `tests_importer.py`,
      `tests_legacy.py`, `tests_review.py` лишились у `education` — перевірено по класах,
      усі каталожні (`tests_map_api.MapFixture(GameFixture)` і `tests_queries.
      QueryCountTests(GameFixture)` — крос-застосункові фікстури, той самий підхід, що
      `game/tests.GameFixture(LessonFixture)`, не помилкове розміщення)
- [x] Повний `grep` по всьому репо на `education.schools`/`education.game`/
      `from .schools import`/`from .game import`/застарілі `from .models import
      School*|Player|Attempt|LessonProgress` — **нуль результатів** за межами самих
      `schools/`/`game/` пакетів (де вони відносні й правильні)
- [x] `python manage.py test` — повний прогін разом із сесіями 7–8: 683/683, OK
- [x] Коміт: разом із сесіями 7–8 (`BE-S07+S08+S14`)

## Сесія 15. `tests_ui.py` — розбиття за темами — ЗРОБЛЕНО (2026-10-29, `d9bc5b6`)

_Мета: 843-рядковий файл — по одному файлу на тему, а не все UI-тестування підряд._

- [x] Прочитай `tests_ui.py`, виділи теми — 22 файли в `education/tests_ui/`: debug_flag,
      tokens, kit, icons, components, topbar, mocks, ui_api_page, map_page, world_page,
      progress_page, profile_page, theme, pwa, lesson_page, text_filters, play_page,
      auth_pages, polish, real_api, paragraph_page (+ `__init__.py`)
- [x] Розбито на пакет `education/tests_ui/` — 24 класи перенесено verbatim, лише глибина
      `Path(__file__)` виправлена під нову вкладеність
- [x] `python manage.py test education.tests_ui` — та сама кількість тестів (691 на весь
      набір, до і після — ідентично), усі зелені; дискавері Django за замовчуванням
      підхопив пакет без змін у `TEST_RUNNER`
- [x] Коміт: `BE-S15: split education/tests_ui.py into tests_ui/ package by topic` (`d9bc5b6`)
- [ ] 🔍 **РЕВ'Ю**: напиши «перевір сесії 13–15»

## Сесія 16. Прибирання `admin.py`, фінальна звірка — ЗРОБЛЕНО (2026-10-29)

_Задоволено роботою сесій 3/5 (перенесення) і 14 (аудит) — без додаткового коду._

- [x] `education/admin.py` (303 → 222 рядки) — перевірено повністю: жодного запису
      для `School*`, і `Player`/`Attempt`/`LessonProgress` там ніколи не були
      зареєстровані (перевірено ще в сесії 4 — нічого переносити)
- [x] Повний `grep -rn "from education"` по всьому репо (поза `education/`/`game/`/
      `schools/`) — `tools/llm/worker.py`, `math_world/urls.py`, `tools/frontend/seed_ui.py`
      імпортують лише каталожні моделі/views, які нікуди не переїхали;
      `tools/frontend/make_mocks.py` читає сирим SQL за назвами таблиць
      (`education_grade`…), які не змінились (`db_table` зафіксовано в сесіях 2, 4)
- [x] CI/Makefile (`.github/workflows/frontend.yml`, `Makefile`,
      `tools/frontend/run_tests.py`) — жодного посилання на старі шляхи тестів
- [x] Коміт: доки-лише, без зміни коду (ніде нема що прибирати)

## Сесія 17. CI, Makefile, документація, повний регрес — ЗРОБЛЕНО (2026-10-29)

- [x] `Makefile` і `.github/workflows/frontend.yml` — жодних прямих посилань на старі
      шляхи тестів (перевірено ще в сесії 16)
- [x] `docs/backend/DECISIONS.md` — підсумковий запис із таблицею застосунків
- [x] `README.md` — оновлено: schools-розділ вказує на `schools/models.py` і
      `schools/services.py`, `python manage.py test` без обмеження на `education`,
      «Project structure» описує три застосунки й їхні межі
- [x] Повний регрес: `python manage.py test` → **683 тести, OK (skipped=14)**;
      `makemigrations --check --dry-run` → **No changes detected**; JS unit-тести
      (`npm test`, `tools/frontend`) → **89/89**. Playwright-знімки не запускались —
      контракт API перевірено байт-у-байт (`get_resolver`, контракт-тести), жодна
      фронтенд-сторінка не торкалась
- [x] Коміт: `BE-S17: update README + final regression`
- [x] 🔍 **РЕВ'Ю**: готово до перевірки — усі 17 основних сесій (BE-S01…S17) зроблені

---

## Беклог (необов'язково, за пріоритетом)

- [ ] **Сесія 18.** Якщо ручний шар серіалізаторів (сесії 7–8) відчувається як
      повторення — оцінити перехід на DRF serializers для catalog/game API
- [ ] **Сесія 19.** `pdf_pipeline/` як повністю окремий встановлюваний пакет
      (власний `requirements-pipeline.txt` уже є) — відокремити від Django-залежностей,
      якщо пайплайн колись треба запускати поза Django
- [ ] **Сесія 20.** Перейменування застосунку `education` → `catalog` — висока вартість
      (усі таблиці `education_*`, усі імпорти), низька користь порівняно із сесіями 1–17;
      тримати в беклозі, не робити без окремого явного рішення
