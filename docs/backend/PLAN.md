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

## Сесія 2. Застосунок `schools` — моделі

_Мета: `School`, `SchoolMembership`, `SchoolClass`, `SchoolClassStudent` переїжджають
у новий застосунок `schools` без зміни таблиць і даних._

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

## Сесія 3. Застосунок `schools` — код і тести

- [ ] Перенеси `education/schools.py` → `schools/services.py`, `education/api_schools.py`
      → `schools/api.py`, `education/tests_schools.py` → `schools/tests.py`
- [ ] Перенеси пов'язані записи `admin.py` → `schools/admin.py`
- [ ] Оновити `education/api_urls.py` → include `schools.urls` (новий файл `schools/urls.py`
      з тими самими шляхами `schools/`, `classes/`…) — зовнішній контракт API не змінюється,
      перевір Playwright/контракт-тестами, що відповіді ті самі
- [ ] Прибери всі старі імпорти `from education.models import School...` по решті коду;
      перевір `grep -rn "from education.models import" | grep -i school`
- [ ] `python manage.py test` — зелено
- [ ] Коміт: `BE-S03: schools app code + tests`
- [ ] 🔍 **РЕВ'Ю**: напиши «перевір сесії 2–3»

## Сесія 4. Застосунок `game` — моделі

- [ ] `python manage.py startapp game`, додай у `INSTALLED_APPS`
- [ ] Перенеси `Player`, `Attempt`, `LessonProgress` тим самим способом, що в сесії 2
      (`db_table` фіксується, `SeparateDatabaseAndState`)
- [ ] FK на `Item`/`Paragraph`/`Exercise`/`SubExercise` лишаються — це нормальний
      крос-застосунковий FK (`education.Item`), Django це підтримує без проблем
- [ ] `makemigrations --check` чистий, тести зелені
- [ ] Коміт: `BE-S04: game models (state-only move)`

## Сесія 5. Застосунок `game` — код і тести

- [ ] `education/game.py` → `game/services.py`, `education/tests_game.py` → `game/tests.py`
- [ ] Відповідні записи `admin.py` → `game/admin.py`
- [ ] `grep -rn "from education.models import" | grep -E "Player|Attempt|LessonProgress"`
      — оновити всі імпорти на `from game.models import ...`
- [ ] `python manage.py test` — зелено
- [ ] Коміт: `BE-S05: game app code + tests`
- [ ] 🔍 **РЕВ'Ю**: напиши «перевір сесії 4–5»

## Сесія 6. Розбиття `api.py` за доменами

_Мета: 367-рядковий `api.py` — по одному файлу на домен, а не всі ендпоінти підряд._

- [ ] `education/api.py` лишає лише catalog-ендпоінти: `textbooks`, `textbook_tree`,
      `grades`, `grade_map`, `lesson_detail`, `lesson_exercise_list`, `exercise_detail`,
      `figure_image`
- [ ] Нове `game/api.py`: `check`, `solution`, `play`, `me`, `_rate_limited`,
      `_payload_text`, `_points_history` (усе, що працює з `Player`/`Attempt`)
- [ ] `schools/api.py` вже існує з сесії 3
- [ ] `education/api_urls.py` стає тонким include: `path("", include("education.api.urls"))`
      + `include("game.urls")` + `include("schools.urls")` (кожен застосунок — свій
      `urls.py` з префіксами, зовнішні шляхи API не змінюються)
- [ ] Контракт-тести (`tools/frontend/check_mocks.py`, `tests_map_api.py`) лишаються
      зеленими без змін у самих тестах — доказ, що контракт не зламано
- [ ] Коміт: `BE-S06: split api.py by domain`

## Сесія 7. Шар серіалізаторів — catalog

_Мета: замінити ручні `*_dict` функції на один explicit шар, а не розкидані по `api.py`._

- [ ] Нове `education/serializers.py`: перенеси `figure_dict`, `subexercise_dict`,
      `exercise_dict`, `block_dict` без зміни форми виводу (контракт той самий)
- [ ] Кожна функція — з docstring/коментарем, яке поле контракту вона реалізує
      (посилання на `mock/README.md`)
- [ ] `education/api.py` імпортує з `serializers.py`, сам файл стає тонким (лише views)
- [ ] Тест: порівняй JSON до/після рефакторингу на реальних fixtures (snapshot-тест,
      якщо такого ще нема — додай)
- [ ] Коміт: `BE-S07: catalog serializers layer`

## Сесія 8. Шар серіалізаторів — game

- [ ] `game/serializers.py`: `progress_dict`, пейлоад `me()` (бали/серія/зірки)
- [ ] `game/api.py` використовує новий шар
- [ ] Контракт-тести (`check_mocks.py`, `tests_api.py` для `/api/me/`) зелені без змін
- [ ] Коміт: `BE-S08: game serializers layer`
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

## Сесія 11. `pdf_pipeline/structure.py` — розбиття

_Мета: 697-рядковий файл на кілька когерентних модулів, без зміни публічного API пайплайна._

- [ ] Прочитай `structure.py` і виділи природні межі (напр.: розбір розділів/параграфів
      окремо від збирання блоків уроку, окремо від нумерації вправ) — запиши межі в
      DECISIONS.md перед тим, як різати файл
- [ ] Перенеси функції в 2–3 нові файли (`structure_sections.py`, `structure_blocks.py`…)
      з тонким `structure.py`, що лише реекспортує публічний інтерфейс для `run.py`
- [ ] `python manage.py test education.tests_pipeline.test_structure` — усі 463 рядки
      тестів лишаються зеленими без змін
- [ ] Коміт: `BE-S11: split pdf_pipeline/structure.py`

## Сесія 12. `pdf_pipeline/vision.py` і `run.py` — розбиття

- [ ] `vision.py` (571 рядок): відділи побудову промптів від розбору відповіді моделі
      від логіки повторних спроб/кешування
- [ ] `run.py` (496 рядків): відділи CLI/аргументи від самого оркестратора кроків пайплайна
- [ ] `python manage.py test education.tests_pipeline` — повний набір зелений
- [ ] Коміт: `BE-S12: split pdf_pipeline vision.py + run.py`
- [ ] 🔍 **РЕВ'Ю**: напиши «перевір сесії 11–12»

## Сесія 13. Домен `review` — межа з catalog

_Мета: `ManualEdit`, `review.py`, `views_review.py`, `templates/education/review/` —
зафіксувати як внутрішній підмодуль catalog (не окремий застосунок: `ManualEdit` жорстко
прив'язаний до `Textbook`/`Exercise`/`SubExercise`, виносити дорожче, ніж тримати)._

- [ ] Запиши в DECISIONS.md явне рішення: review НЕ стає окремим застосунком, і чому
- [ ] Перенеси `review.py`, `views_review.py` під `education/review/` як пакет
      (`education/review/services.py`, `education/review/views.py`), якщо це покращує
      навігацію — інакше залиш як є й зафіксуй це рішення замість переносу
- [ ] `python manage.py test education.tests_review` — зелено
- [ ] Коміт: `BE-S13: review module boundary` (або просто запис рішення, якщо без переносу)

## Сесія 14. Тести: розкладка по застосунках

- [ ] `schools/tests.py` і `game/tests.py` вже існують (сесії 3, 5) — перевір, що там
      лише тести свого домену, а не випадково залишені чужі
- [ ] `tests_api.py`, `tests_map_api.py`, `tests_queries.py`, `tests_models.py`,
      `tests_commands.py`, `tests_cache_tools.py`, `tests_backup.py`, `tests_importer.py`
      лишаються в `education` (catalog) — це його домен; перевір, що жоден тест не
      імпортує вже перенесені моделі напряму зі старого шляху
- [ ] `python manage.py test` — повний прогін, фінальна кількість тестів не менша за
      базову лінію з сесії 1
- [ ] Коміт: `BE-S14: test layout matches app boundaries`

## Сесія 15. `tests_ui.py` — розбиття за темами

_Мета: 843-рядковий файл — по одному файлу на тему, а не все UI-тестування підряд._

- [ ] Прочитай `tests_ui.py`, виділи теми (токени/кит, іконки, топбар, мапа, панель уроку,
      доступність…) — запиши список тем
- [ ] Розбий на `tests_ui/test_tokens.py`, `tests_ui/test_topbar.py`, `tests_ui/test_map.py`…
      (пакет `tests_ui/` замість одного файлу)
- [ ] `python manage.py test education.tests_ui` — та сама кількість тестів, усі зелені
- [ ] Коміт: `BE-S15: split tests_ui.py by topic`
- [ ] 🔍 **РЕВ'Ю**: напиши «перевір сесії 13–15»

## Сесія 16. Прибирання `admin.py`, фінальна звірка

- [ ] `education/admin.py` (303 рядки до рефакторингу) — перевір, що записи для
      `School*`/`Player`/`Attempt`/`LessonProgress` вже переїхали в сесіях 3, 5;
      прибери залишки/дублікати
- [ ] Повний `grep -rn "from education" --include="*.py"` по всьому репо — жодного
      застарілого імпорту з перенесених доменів
- [ ] `python manage.py test` — зелено
- [ ] Коміт: `BE-S16: admin cleanup + import audit`

## Сесія 17. CI, Makefile, документація, повний регрес

- [ ] `Makefile` і `.github/workflows/frontend.yml` — перевір, чи там є прямі посилання
      на `education.tests_*` за старими шляхами, оновити
- [ ] `docs/backend/DECISIONS.md` — підсумковий запис: фінальна карта застосунків
      (`education`/catalog, `schools`, `game`), що залишилось мертвим кодом і чому,
      що винесено в беклог
- [ ] `README.md` — оновити розділ про структуру проєкту, якщо він описує старі межі
- [ ] Повний `python manage.py test` + Playwright дим-тест (`tools/frontend` знімки
      ключових сторінок) — порівняти з базовою лінією сесії 1
- [ ] Коміт: `BE-S17: CI/docs + final regression`
- [ ] 🔍 **РЕВ'Ю**: напиши «перевір сесію 17 — готово до мерджу»

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
