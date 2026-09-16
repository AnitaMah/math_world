# Math World — Refactoring Plan: Design & Parsing Logic

Date: 2026-09-15 (updated 2026-09-16 — reconciled against actual codebase
state; a lot of the checklist below was already done without the
checkboxes ever being updated. See the note at the top of Section 3.)

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

**Resolved:** `import_programm_csv.py` and the hand-typed CSV have since
been deleted from the codebase; `import_curriculum` is the only importer
now (Step 3's decision — see Section 3).

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
Tesseract OCR with the Ukrainian language pack (`tesseract-ocr-ukr`) --
this produces clean, accurate Ukrainian text. Verified against several
real pages including exercise lists with numbers, fractions, and mixed
Cyrillic/Latin math notation. **Implemented:** `scripts/render_pdf_pages.py`
+ `scripts/ocr_pages.py` (Steps 12–13, done — see Section 3).

### 1.4 The data model is thinner than the actual content
`Item.content` is currently just a title string. A real lesson ("пункт")
contains, in order: theory text, a numbered self-check question block, a
"Розв'язуємо усно" (mental-math) exercise list, a "Вправи" (written
exercises) list with difficulty markers (°, plain, ··, *), a "Вправи для
повторення" (review) list, one "Задача від Мудрої Сови" problem, and an
optional "Коли зроблено уроки" historical aside. That's a genuine mix of
**narrative Ukrainian text** and **structured math problems** — two kinds
of content that need different modeling. This is the "text and math
stuff" you flagged. **Implemented:** the `ContentBlock` model (Section 2,
Steps 8–10, done).

### 1.5 No `Subject` concept
`Grade` is keyed only by `number`. If math world is meant to cover
multiple Ukrainian school subjects per grade, a second subject's 5th
grade would collide with math's 5th grade under the same `Grade` row.
**Implemented:** `Subject` model, `Grade.subject` FK (now required),
Steps 4–7, done.

## 2. Target design (what we're building toward)

```
Subject(code, name_uk, name_de)                 # DONE
Grade(number, subject FK, name_uk, name_de,      # DONE (subject required)
      theme_uk, theme_de)
Section(grade FK, number, name_uk, name_de)       # unchanged shape
Paragraph(section FK, number, name_uk, name_de)   # unchanged shape
Item(paragraph FK, number, content, content_de,   # "content" is still
     type, image_path)                            #  theory/title text
ContentBlock(item FK, block_type, order,          # DONE (table + admin +
             text, difficulty, image_path)         #  item_detail render).
                                                     #  Table is still
                                                     #  EMPTY of real data
                                                     #  (Steps 21-23 not
                                                     #  run yet).
```

`block_type` choices (as implemented): `theory`, `self_check`,
`oral_exercise`, `exercise`, `review_exercise`, `wise_owl`,
`history_aside`. `difficulty` choices: `basic` (°), `standard`,
`advanced` (··), `olympiad` (*) — for `exercise` rows.

This was a real migration touching the existing `db.sqlite3`, done in the
small, independently-checkable steps below.

## 3. Small steps

**Status note (2026-09-16):** the checklist below was last updated when
only Step 0 was checked off, but the actual codebase has since
implemented Steps 1–16 (with a couple of caveats noted inline) plus an
entire unplanned sub-project (Gemini-vision-assisted OCR, see the new
section at the end). Re-verify this list periodically instead of trusting
old checkmarks — that's exactly the drift that caused this out-of-date
read.

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

### Verify Phase 1
- [x] **Step 1** — `python manage.py test education` — grade-5 import
      tests pass. (2026-09-16: the `ContentClassifierTests` suite added
      later, for Steps 15–16, had a real regression here — the exercise
      difficulty-marker regex expected the marker *before* the period
      instead of after it, e.g. matching `2".` instead of the actual
      `2."` OCR output. Fixed and pushed as commit `8a7b37a`.)
- [x] **Step 2** — `import_curriculum` has been run against the real
      `db.sqlite3` for grade 5 (status `"imported"` in
      `data/grade_sources.py`) — 2 sections / 5 paragraphs / 38 items
      confirmed.
- [x] **Step 3** — Decided: deleted. `import_programm_csv.py` and the old
      hand-typed CSV no longer exist in the codebase; `import_curriculum`
      is the only importer.

### Data model: Subject (small, low-risk — additive only)
- [x] **Step 4** — `Subject` model exists (`code`, `name_uk`, `name_de`).
- [x] **Step 5–7** — `Grade.subject` FK added, backfilled (migration
      `0010_backfill_grade_subject.py`), and made non-nullable
      (`0011_grade_subject_required.py`). `import_curriculum` accepts
      `--subject-code` and sets it on `get_or_create`.

### Data model: ContentBlock (additive — doesn't touch existing fields)
- [x] **Step 8** — `ContentBlock` model exists (migrations `0012`, `0013`).
- [x] **Step 9** — `ContentBlockInline` registered under `ItemAdmin` in
      `admin.py`.
- [x] **Step 10** — `item_detail` view groups `item.content_blocks` by
      `block_type` and the template renders each group (with a muted
      fallback when a lesson has none yet).
- [ ] **Step 11** — `item_list`/`mint_overview` still render from
      `Item.details_list()` (splitting `Item.content` by line/sentence),
      not from `ContentBlock` rows — they haven't been revisited since
      Step 10 only touched `item_detail`. Still open.

### Content extraction: build the pipeline one block type at a time
- [x] **Step 12** — `scripts/render_pdf_pages.py` (wraps `pdftoppm`).
- [x] **Step 13** — `scripts/ocr_pages.py` (Tesseract, `-l ukr --psm 6`).
- [x] **Step 14** — §1 (pages 5–15) rendered + OCR'd into `review/section_1`
      and `review/section_1_text/` (including `combined.txt`), used
      directly as real test fixtures in `education/tests.py`.
- [x] **Step 15** — `find_review_exercise_blocks()` in
      `education/parsing/content_classifier.py`, tested against real OCR
      text from `combined.txt`.
- [x] **Step 16** — `find_exercise_blocks()`, capturing each item's
      difficulty marker. (This is the function whose regex had the bug
      fixed in Step 1 above.)
- [ ] **Step 17** — `oral_exercise` ("Розв'язуємо усно") classifier — not
      started. `content_classifier.py` only implements `review_exercise`
      and `exercise` so far.
- [ ] **Step 18** — `wise_owl` ("Задача від Мудрої Сови") classifier —
      not started.
- [ ] **Step 19** — `history_aside` ("Коли зроблено уроки") classifier —
      not started; still expected to be the hardest (spans a page-layout
      box).
- [~] **Step 20** — Implemented differently than planned: instead of a
      `--dry-run` flag on `import_curriculum`, there's a standalone
      `scripts/classify_content.py` CLI that runs a chosen classifier
      (`review_exercise` or `exercise`) over a text file and prints the
      result — same dry-run spirit, separate tool. Decide whether to fold
      this into `import_curriculum --dry-run` as originally planned, or
      keep it standalone and extend it as Steps 17–19 land.
- [ ] **Step 21** — Dry-run output for §1 hasn't been read through by hand
      end-to-end and reconciled against the real book yet (beyond the
      regex bug already found via the test suite).
- [ ] **Step 22** — Nothing has been written for real to `ContentBlock`
      yet — the table is still empty except whatever was manually typed
      in the admin to validate Step 9. This is the actual next concrete
      step once Steps 17–19 (or a decision to skip them for now and just
      import `review_exercise`/`exercise`) are ready.
- [ ] **Step 23** — Not started (depends on Step 22 landing for §1 first).
- [ ] **Step 24** — Not started; only pages 1–46 of the grade-5 PDF are in
      the project so far.

### Generalizing across textbooks and subjects
This section didn't play out the way it was originally planned — worth
rewriting rather than just checking boxes.

- [x] **Multi-textbook generalization (unplanned, done ahead of schedule)**
      — `SubjectProfile` in `subject_profiles.py` was generalized to be
      keyed by *textbook/author*, not by subject or grade number. This
      is what let grade 6 (Тарасенкова, `math_tarasenkova` profile, still
      the "math" subject) get added alongside grade 5 (Мерзляк,
      `math_merzlyak`) without any model changes — see the profile file's
      own "NOTE ON GRADES 5-9" comment. `data/grade_sources.py` is a new
      manifest (not originally planned) tracking per-grade source status;
      grade 6 is currently `"sections_only_no_items"` since its table of
      contents has no individual lesson titles to extract yet (Тарасенкова's
      "Зміст" only lists Розділ/§, per the profile's own comment —
      referenced there as "Step 36", i.e. a future step, of extracting
      lesson titles from each §'s actual pages).
- [ ] **A genuinely different subject** (e.g. `ukr_language`) — a
      `UKR_LANGUAGE_PROFILE` already exists as a *starting point* in
      `subject_profiles.py`, but there's no real Ukrainian-language-arts
      source text imported yet. This is what the original Steps 25–26
      were actually about; still open.

## 4. Unplanned sub-project: Gemini-vision-assisted OCR

Not in the original plan at all, but present in the codebase (the code's
own comments number these "Steps 27–29", continuing on from Step 26
above):

- [x] **("Step 27")** `scripts/gemini_client.py` — a quota-conscious
      Gemini API wrapper: disk-cached responses (never re-spends quota on
      a repeated request), a hard daily request budget, and one retry
      with backoff on 429/503. Deliberately doesn't hardcode a model name
      — reads `GEMINI_MODEL` from the environment since Google's free-tier
      model lineup has moved more than once in 2026.
- [x] **("Step 28")** `education/parsing/math_heuristic.py` —
      `needs_vision_ocr()`, a free, local (no API call) heuristic that
      flags OCR'd text likely to contain mangled math notation (explicit
      marker phrases like "обчисліть", math symbols, or a high density of
      short garbled digit/symbol tokens). This is the quota gate for the
      next step. Tested in `MathHeuristicTests`.
- [ ] **("Step 29") Gemini vision OCR re-pass** — `GeminiClient.generate_from_image()`
      exists and is ready to call, but nothing in the pipeline actually
      invokes it yet on blocks `math_heuristic.py` flags. This is the
      real next piece of this sub-project: wire flagged blocks from the
      OCR/classification pipeline into a `generate_from_image` call and
      use the result in place of Tesseract's output for just those
      blocks.
- [ ] **("Step 30")** A `--vision-ocr` flag (mentioned in
      `math_heuristic.py`'s own docstring) to turn this on for a given
      `import_curriculum` run once Step 29 exists.

## 5. Open decisions (only block the steps below, not what's already done)

- **Steps 17–19 vs. skipping ahead:** worth deciding whether to finish
  the remaining three classifiers (`oral_exercise`, `wise_owl`,
  `history_aside`) before writing anything real to the DB (Step 22), or
  import just `review_exercise`/`exercise` for §1 now and backfill the
  other block types in a later pass. Either is fine; picking one avoids
  stalling on completeness.
- **Step 20's shape:** keep `scripts/classify_content.py` as a standalone
  dry-run CLI, or fold it into `import_curriculum --dry-run` as
  originally planned.
- **Step 11:** decide whether `item_list`/`mint_overview` are worth
  updating to read from `ContentBlock` now, or only once Step 22 actually
  populates real content-block rows (updating the UI before there's real
  data to show it may not be worth doing yet).
- Steps 12–24 still need the rest of the grade-5 textbook PDF eventually
  (only pages 1–46 are in the project); fine to keep pausing at Step 24
  until more pages are available.
- ("Step 29") needs a live `GEMINI_API_KEY` and a confirmed model name
  (run `scripts/list_gemini_models.py` first) before it can be wired up.

## 6. Files delivered so far

```
education/parsing/__init__.py
education/parsing/subject_profiles.py
education/parsing/toc_parser.py
education/parsing/content_classifier.py        (Steps 15-16)
education/parsing/math_heuristic.py            ("Step 28")
education/management/commands/import_curriculum.py
education/tests.py                             (repeatedly extended)
education/models.py                            (Subject, ContentBlock added)
education/admin.py                             (ContentBlockInline, SubjectAdmin)
education/views.py / templates/item_detail.html (ContentBlock rendering)
scripts/render_pdf_pages.py                    (Step 12)
scripts/ocr_pages.py                           (Step 13)
scripts/classify_content.py                    (Step 20, standalone form)
scripts/gemini_client.py                       ("Step 27")
scripts/list_gemini_models.py
data/5_class_ukr.txt                           (corrected fixture, grade 5)
data/6_class_ukr.txt                           (grade 6, sections/§ only)
data/grade_sources.py                          (new: per-grade status manifest)
review/section_1/, review/section_1_text/      (Step 14 output, real OCR fixtures)
```
