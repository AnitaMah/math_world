# Math World — Refactoring Plan: Design & Parsing Logic

Date: 2026-09-15
Scope: `education` app data model, curriculum ingestion pipeline, and the
concrete parsing bug that motivated this refactor.

## 1. What's actually broken (diagnosis)

I read through the codebase and the actual source PDF (`5-klas-matematika-merzljak-2018`,
pages 1–46) rather than just the derived files, and found three distinct
problems hiding under "parsing troubles":

### 1.1 The real importer was never built
`education/management/commands/import_programm_csv.py` requires a
hand-typed CSV (`programm/5_class_ukr.csv`) — someone manually retyped the
entire table of contents. `education/tests.py` already references a
different, smarter command (`import_curriculum`, with `--file`/`--grade`/
`--language`/`--reset` args, reading a raw `.txt` directly) that **did not
exist anywhere in the codebase**, and its expected fixture file
(`data/5_class_ukr.txt`) didn't exist either. The test suite had been
failing/erroring from the start.

### 1.2 The `.txt`/`.csv` source itself is wrong, not just the code
Comparing `5_class_ukr.txt` against the actual textbook pages, the
structural headings (Розділ / § / numbered lessons) are all correct, but
the file is **missing content**: pages 12–15 of the real book show item 2
("Цифри. Десятковий запис натуральних чисел") has *two* "Коли зроблено
уроки" historical asides, and only one bullet like this survived anywhere
in the whole file (attached to a different item, item 3).

### 1.3 The deeper cause: the PDF's embedded text is corrupted
Extracting text from your PDF with `pdftotext`/`pypdf` (the standard
approach) comes out with Cyrillic **systematically swapped for Latin
look-alikes** — e.g. "Назва" → `HasBa`, "своєї" → `cBoei`, "на" → `Ha`.
This is a broken/custom font-encoding table embedded in the PDF (it was
run through iLovePDF, which can do this). **Any pipeline that extracts
text from this PDF the normal way will silently produce garbled
Ukrainian.**

Confirmed fix: render each page to an image (`pdftoppm`, 300dpi) and run
Tesseract OCR with the Ukrainian language pack (`tesseract-ocr-ukr`) —
this produces clean, accurate Ukrainian text. Verified against several
real pages including exercise lists with numbers, fractions, and mixed
Cyrillic/Latin math notation.

### 1.4 The data model is thinner than the actual content
`Item.content` is currently just a title string. A real lesson ("пункт")
contains, in order: theory text, a numbered self-check question block, a
"Розв'язуємо усно" (mental-math) exercise list, a "Вправи" (written
exercises) list with difficulty markers (°, plain, ··, *), a "Вправи для
повторення" (review) list, one "Задача від Мудрої Сови" problem, and an
optional "Коли зроблено уроки" historical aside. That's a genuine mix of
**narrative Ukrainian text** and **structured math problems** — two kinds
of content that need different modeling. This is the "text and math
stuff" you flagged.

### 1.5 No `Subject` concept
`Grade` is keyed only by `number`. If math world is meant to cover
multiple Ukrainian school subjects per grade, a second subject's 5th
grade would collide with math's 5th grade under the same `Grade` row.

## 2. Target design (what we're building toward)

```
Subject(code, name_uk, name_de)                 # NEW — e.g. "math", "ukr_mova"
Grade(number, subject FK, name_uk, name_de,      # subject added
      theme_uk, theme_de)
Section(grade FK, number, name_uk, name_de)       # unchanged shape
Paragraph(section FK, number, name_uk, name_de)   # unchanged shape
Item(paragraph FK, number, content, content_de,   # "content" becomes the
     type, image_path)                            #  theory text only
ContentBlock(item FK, block_type, order,          # NEW — one row per
             text, difficulty, image_path)         #  self-check / oral /
                                                     #  exercise / review /
                                                     #  wise-owl / history
```

`block_type` choices: `self_check`, `oral_exercise`, `exercise`,
`review_exercise`, `wise_owl`, `history_aside`. `difficulty` (nullable)
holds the °/·/··/* marker for `exercise` rows.

This is a real migration touching your existing `db.sqlite3`, which is
why it's broken into small, independently-checkable steps below rather
than one big change.

## 3. Small steps

Each step is meant to be one sitting, independently testable, and safe to
stop after. Do them in order — later steps assume earlier ones landed.

### Done already
- [x] **Step 0** — Diagnosed the three problems above; built and validated
      the skeleton importer: `education/parsing/subject_profiles.py`,
      `education/parsing/toc_parser.py`,
      `education/management/commands/import_curriculum.py`, corrected
      `data/5_class_ukr.txt`, rewritten `education/tests.py`. Verified:
      2 sections, 5 paragraphs, 38 items, 15 noise lines correctly
      skipped, historical aside merged into the right item.

### Next: verify Phase 1 on your machine
- [ ] **Step 1** — Run `python manage.py test education` and confirm all
      4 tests pass.
- [ ] **Step 2** — Run
      `python manage.py import_curriculum --file data/5_class_ukr.txt --grade 5 --language uk --reset`
      against your real `db.sqlite3` (back it up first — copy
      `db.sqlite3` somewhere safe) and check the admin site shows 2
      sections / 5 paragraphs / 38 items for grade 5.
- [ ] **Step 3** — Decide: keep `import_programm_csv.py` around (marked
      deprecated in its `help` text) or delete it + the CSV now that
      Step 2 works. Small either way, but pick one so it doesn't rot.

### Data model: Subject (small, low-risk — additive only)
- [ ] **Step 4** — Add `Subject` model (just the table, no FK from Grade
      yet). Migrate. Seed one row: `Subject(code="math", name_uk="Математика")`.
- [ ] **Step 5** — Add `subject` FK to `Grade`, nullable for now. Migrate.
      Nothing else changes yet — existing code keeps working.
- [ ] **Step 6** — Data migration: set `subject_id` on every existing
      `Grade` row to the "math" Subject. Verify in admin.
- [ ] **Step 7** — Make `Grade.subject` non-nullable. Migrate. Update
      `import_curriculum` to accept `--subject-code` and set it on
      `get_or_create`.

### Data model: ContentBlock (additive — doesn't touch existing fields)
- [ ] **Step 8** — Add `ContentBlock` model (empty table, no data). Migrate.
- [ ] **Step 9** — Register `ContentBlock` as a `TabularInline` under
      `ItemAdmin` in `admin.py` (same pattern as `TheoryPracticeInline`),
      so you can manually add one row and see it work before any
      automated parsing touches it.
- [ ] **Step 10** — Update `item_detail` view/template only (not
      `item_list`/`mint_overview` yet) to render an item's `ContentBlock`
      rows grouped by `block_type`, falling back gracefully when there
      are none. Smallest possible UI change to prove the model works.
- [ ] **Step 11** — Once Step 10 looks right for a manually-entered test
      block, revisit `item_list`/`mint_overview`'s `lstrip("• ")`
      heuristic and simplify it now that structure doesn't need to be
      guessed from bullet characters.

### Content extraction: build the pipeline one block type at a time
- [ ] **Step 12** — `scripts/render_pdf_pages.py`: wraps `pdftoppm` to
      render one page range to PNG. Test on a single page (e.g. page 5).
- [ ] **Step 13** — `scripts/ocr_pages.py`: runs Tesseract
      (`-l ukr --psm 6`) over rendered PNGs, writes one `.txt` per page.
      Test on the same single page and diff against what I already
      verified in this conversation.
- [ ] **Step 14** — Run Steps 12–13 over just §1 (pages 5–15) and save
      the raw OCR text to a `review/` folder — no parsing yet, just look
      at it and confirm quality on a whole section.
- [ ] **Step 15** — Write a classifier for **one** block type only:
      `review_exercise` ("Вправи для повторення" — the clearest, least
      ambiguous marker). Run it over the §1 OCR text, print what it
      would create, don't touch the DB yet.
- [ ] **Step 16** — Add `exercise` (the "Вправи" list, capturing the
      difficulty marker). Same dry-run treatment.
- [ ] **Step 17** — Add `oral_exercise` ("Розв'язуємо усно").
- [ ] **Step 18** — Add `wise_owl` ("Задача від Мудрої Сови" — usually
      exactly one per item, simplest to detect).
- [ ] **Step 19** — Add `history_aside` ("Коли зроблено уроки" — hardest,
      spans a page-layout box; do this last).
- [ ] **Step 20** — Add a `--dry-run` flag to `import_curriculum` that
      prints the `ContentBlock`s it would create for a given file/range
      without writing them, wired to the classifiers from Steps 15–19.
- [ ] **Step 21** — Run `--dry-run` over §1, read through the output by
      hand, fix classifier mistakes.
- [ ] **Step 22** — Run for real (writes to DB) for §1 only. Check in
      admin. This is the first end-to-end slice: PDF → OCR → blocks → DB → admin.
- [ ] **Step 23** — Repeat Steps 14–22 section by section for the rest of
      grade 5 math that's in this PDF (pages 1–46 only cover part of the
      book).
- [ ] **Step 24** — Get the rest of the textbook PDF (or specific
      chapters you want next) before continuing past what's already
      uploaded.

### Generalizing beyond math
- [ ] **Step 25** — Once a second subject's real source text exists, add
      its `SubjectProfile` in `subject_profiles.py`.
- [ ] **Step 26** — If that subject's lesson pages use different sidebar
      types than math's, extend `ContentBlock.block_type` rather than
      branching the parser by subject name.

## 4. Open decisions (only block Steps 4+ / 12+, not the steps already done)

- Confirm the `ContentBlock` shape in Section 2 (or say what's wrong)
  before Step 8's migration touches your live `db.sqlite3`.
- Steps 12–24 need the rest of the textbook PDF eventually — fine to
  start with just pages 1–46 and pause at Step 24.
- Step 3's call on `import_programm_csv.py`/the old CSV.

## 5. Files delivered so far (Step 0)

```
education/parsing/__init__.py
education/parsing/subject_profiles.py
education/parsing/toc_parser.py
education/management/commands/import_curriculum.py
education/tests.py                    (rewritten)
data/5_class_ukr.txt                  (corrected fixture)
```
