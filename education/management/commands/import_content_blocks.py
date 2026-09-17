"""
Step 22: writes real ContentBlock rows from a raw OCR text file, using the
same classifiers Steps 15-19 built and the same dry-run preview shape
Step 20 already prints (collect_content_block_previews). This is the first
command in the pipeline that actually touches the ContentBlock table --
everything before this only ever printed candidates for review (Step 21).

A ContentBlock belongs to one Item (one numbered lesson, e.g. "1. Ряд
натуральних чисел"), but the classifiers only know line numbers in the
raw text -- they have no idea which Item a block is "inside". This
command bridges that gap by finding each Item's own title line in the
raw text (already known, since the TOC importer stored it as Item.content)
and using those line numbers as boundaries: a block belongs to whichever
Item's title line is the last one at or before the block's start_line.

Usage:
    python manage.py import_content_blocks --content-file review/section_1_text/combined.txt \\
        --grade 5 --section 1 --paragraph 1 [--dry-run] [--reset]

--dry-run prints the same block-to-item mapping this command would write,
without touching the database -- use this first to sanity-check the
mapping before writing for real (same discipline as Step 20/21).
--reset deletes existing ContentBlocks for this paragraph's items first,
so re-running after fixing a classifier doesn't pile up duplicates.

Step 29: --vision-ocr re-corrects just the blocks math_heuristic.py flags
as likely to contain mangled math notation, by sending the *source page
image* (not the OCR text) to Gemini and asking for a clean transcription
of that one passage. This only ever touches flagged blocks -- most of a
lesson's text is fine as plain Tesseract OCR, and Gemini's free-tier quota
is finite, so paying for a vision call on every block would be wasteful
for no benefit on the ~40% of blocks that are already clean.

Needs --pages-dirs (PNG directories, e.g. "review/section_1,review/section_1_rest")
and --pages-text-dirs (the matching OCR .txt directories used to build
--content-file, in the same page order) to work out which page image a
given block actually came from -- see _build_line_to_page_map below.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import ContentBlock, Item, Paragraph
from education.parsing.content_classifier import collect_content_block_previews
from education.parsing.math_heuristic import needs_vision_ocr

PAGE_FILENAME_RE = re.compile(r"page-(\d+)\.(\w+)$")


def _find_item_boundaries(raw_lines: list[str], items: list[Item]) -> list[tuple[int, Item]]:
    """
    For each Item (in number order), finds the line in raw_lines where its
    lesson actually starts -- i.e. the numbered title line matching
    Item.content's first line (e.g. "1. Ряд натуральних чисел"). Returns
    (start_line, item) pairs in the same order as `items`.

    Searches forward from the end of the previous item's boundary so an
    earlier, unrelated line that happens to repeat the same words (a
    running page header, say) can't be matched before the real one --
    the same "don't trust anything but forward progress" caution used by
    the classifiers themselves (MAX_ITEM_NUMBER_JUMP, the exercise
    "increasing number" guard, etc.).

    An item whose title line can't be found at all is skipped (not
    raised) -- this raw text file may simply not cover that lesson yet
    (e.g. combined.txt only has pages 5-15, not the whole book), which is
    an expected, not exceptional, case for a partial OCR fixture.
    """
    boundaries: list[tuple[int, Item]] = []
    search_from = 0

    for item in items:
        title_first_line = item.content.strip().splitlines()[0].strip()
        marker = re.compile(
            r"^" + re.escape(f"{item.number}.") + r"\s*" + re.escape(title_first_line) + r"\s*$"
        )
        for i in range(search_from, len(raw_lines)):
            if marker.match(raw_lines[i].strip()):
                boundaries.append((i, item))
                search_from = i + 1
                break

    return boundaries


def _assign_previews_to_items(previews: list[dict], boundaries: list[tuple[int, Item]]):
    """
    Walks previews in document order (they're already sorted by
    start_line -- see collect_content_block_previews) and hands each one
    to whichever item's boundary is the last one at or before its
    start_line. A preview that starts before the *first* known boundary
    (e.g. the oral warm-up questions that open a lesson, before its own
    numbered title line reappears mid-page) is attached to that first
    item rather than dropped -- it's still real content for that lesson,
    it just happens to sit above the lesson's own title line in the raw
    OCR text.
    """
    assigned: list[tuple[dict, Item]] = []
    if not boundaries:
        return assigned

    b_idx = 0
    for preview in previews:
        while (
            b_idx + 1 < len(boundaries)
            and boundaries[b_idx + 1][0] <= preview["start_line"]
        ):
            b_idx += 1
        assigned.append((preview, boundaries[b_idx][1]))

    return assigned


def _collect_numbered_files(dirs: list[Path], suffix: str) -> dict[int, Path]:
    """
    {page_number: path} for every "page-NN.<suffix>" file across `dirs`.
    Used for both the PNG dirs (--pages-dirs) and the OCR .txt dirs
    (--pages-text-dirs) -- same naming convention, different suffix.
    """
    mapping: dict[int, Path] = {}
    for d in dirs:
        for f in Path(d).glob(f"page-*.{suffix}"):
            m = PAGE_FILENAME_RE.match(f.name)
            if m:
                mapping[int(m.group(1))] = f
    return mapping


def _build_line_to_page_map(text_files: dict[int, Path]) -> list[tuple[int, int]]:
    """
    [(first_line_of_page, page_number), ...] sorted by page number,
    assuming --content-file is a plain concatenation of these page .txt
    files in ascending page-number order (that's how combined.txt has
    been built since Step 14 -- confirmed by diffing against a plain
    `cat` of the page files, not just assumed).
    """
    boundaries: list[tuple[int, int]] = []
    offset = 0
    for page_num in sorted(text_files):
        boundaries.append((offset, page_num))
        offset += len(text_files[page_num].read_text(encoding="utf-8").splitlines())
    return boundaries


def _page_for_line(boundaries: list[tuple[int, int]], line_no: int) -> int:
    page = boundaries[0][1]
    for start, num in boundaries:
        if start <= line_no:
            page = num
        else:
            break
    return page


VISION_OCR_PROMPT_VERSION = "v1"


def _vision_ocr_prompt(ocr_text: str) -> str:
    return (
        "Це сторінка українського підручника з математики для 5 класу. "
        "Наступний уривок було отримано за допомогою Tesseract OCR і в ньому "
        "є помилки -- особливо в математичних записах (сплутані цифри, "
        "пропущені або зайві символи, побитий інтервал):\n\n"
        f"{ocr_text}\n\n"
        "Подивись на зображення сторінки і дай ВИПРАВЛЕНУ транскрипцію "
        "ЛИШЕ цього уривка (не всієї сторінки), зберігаючи переноси рядків "
        "і нумерацію завдань. Поверни тільки виправлений текст, без "
        "жодних пояснень чи коментарів."
    )


class Command(BaseCommand):
    help = (
        "Записує реальні ContentBlock з сирого OCR-тексту, зіставляючи кожен "
        "блок з відповідним пунктом (Item) за рядком його заголовка (Step 22). "
        "--vision-ocr додатково виправляє математично-важкі блоки через Gemini "
        "vision (Step 29)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--content-file", required=True)
        parser.add_argument("--grade", type=int, required=True)
        parser.add_argument("--section", type=int, required=True, help="Номер розділу")
        parser.add_argument("--paragraph", type=int, required=True, help="Номер §")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показати зіставлення блок->пункт без запису у БД",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Видалити наявні ContentBlock цих пунктів перед записом",
        )
        parser.add_argument(
            "--vision-ocr",
            action="store_true",
            help=(
                "Виправити текст блоків, позначених math_heuristic.needs_vision_ocr, "
                "через Gemini vision (Step 29). Потребує --pages-dirs і "
                "--pages-text-dirs."
            ),
        )
        parser.add_argument(
            "--pages-dirs",
            default=None,
            help="Кома-розділений список директорій з page-NN.png (для --vision-ocr)",
        )
        parser.add_argument(
            "--pages-text-dirs",
            default=None,
            help=(
                "Кома-розділений список директорій з page-NN.txt, у тому ж порядку "
                "сторінок, що й --content-file (для --vision-ocr)"
            ),
        )
        parser.add_argument(
            "--vision-ocr-limit",
            type=int,
            default=None,
            help="Обмежити кількість блоків, виправлених через Gemini (для тестування)",
        )

    def handle(self, *args, **options):
        content_path = Path(options["content_file"])
        if not content_path.exists():
            raise CommandError(f"Файл не знайдено: {content_path}")

        try:
            paragraph = Paragraph.objects.get(
                number=options["paragraph"],
                section__number=options["section"],
                section__grade__number=options["grade"],
            )
        except Paragraph.DoesNotExist:
            raise CommandError(
                f"Не знайдено § {options['paragraph']} у розділі {options['section']}, "
                f"клас {options['grade']} -- спершу маємо бути результати import_curriculum."
            )

        items = list(Item.objects.filter(paragraph=paragraph).order_by("number"))
        if not items:
            raise CommandError(f"У §{paragraph.number} немає жодного пункту (Item).")

        raw_text = content_path.read_text(encoding="utf-8")
        raw_lines = raw_text.splitlines()

        boundaries = _find_item_boundaries(raw_lines, items)
        if not boundaries:
            raise CommandError(
                "Жодного заголовка пункту не знайдено у файлі -- перевірте, чи цей "
                "--content-file справді відповідає --section/--paragraph."
            )

        found_items = {item.number for _, item in boundaries}
        missing = [item.number for item in items if item.number not in found_items]
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    f"ℹ️ Пункти {missing} не знайдені у файлі (текст їх не покриває) -- "
                    f"це очікувано для часткового OCR-файлу, пропускаємо."
                )
            )

        previews = collect_content_block_previews(raw_text)
        assigned = _assign_previews_to_items(previews, boundaries)

        if options["vision_ocr"]:
            self._apply_vision_ocr(options, assigned)

        if options["dry_run"]:
            self.stdout.write(
                f"Зіставлення {len(assigned)} блок(ів) із {content_path} "
                f"(DRY RUN -- нічого не записано в БД):\n"
            )
            for preview, item in assigned:
                tag = f" [{preview['difficulty']}]" if preview["difficulty"] else ""
                text = preview["text"]
                if len(text) > 120:
                    text = text[:120] + "…"
                self.stdout.write(
                    f"  Пункт {item.number} ({item.content.splitlines()[0][:40]}) "
                    f"<- {preview['block_type']}{tag}: {text}"
                )
            return

        with transaction.atomic():
            if options["reset"]:
                deleted, _ = ContentBlock.objects.filter(item__in=items).delete()
                if deleted:
                    self.stdout.write(
                        self.style.WARNING(f"ℹ️ Видалено {deleted} наявних ContentBlock.")
                    )

            order_by_item: dict[int, int] = {}
            created = 0
            for preview, item in assigned:
                order = order_by_item.get(item.id, 0)
                ContentBlock.objects.create(
                    item=item,
                    block_type=preview["block_type"],
                    order=order,
                    text=preview["text"],
                    difficulty=preview["difficulty"],
                )
                order_by_item[item.id] = order + 1
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Записано {created} ContentBlock(ів) для §{paragraph.number} "
                f"({len(found_items)} пункт(и) з {len(items)})."
            )
        )

    def _apply_vision_ocr(self, options, assigned: list[tuple[dict, Item]]) -> None:
        if not options["pages_dirs"] or not options["pages_text_dirs"]:
            raise CommandError("--vision-ocr вимагає --pages-dirs і --pages-text-dirs")

        png_dirs = [Path(p.strip()) for p in options["pages_dirs"].split(",")]
        text_dirs = [Path(p.strip()) for p in options["pages_text_dirs"].split(",")]

        png_files = _collect_numbered_files(png_dirs, "png")
        text_files = _collect_numbered_files(text_dirs, "txt")
        line_boundaries = _build_line_to_page_map(text_files)

        # Imported lazily: this command works fine without google-genai
        # installed as long as --vision-ocr is never passed.
        from scripts.gemini_client import GeminiBudgetExceeded, GeminiClient

        client = GeminiClient()

        flagged = [
            (preview, item) for preview, item in assigned if needs_vision_ocr(preview["text"])
        ]
        limit = options["vision_ocr_limit"]
        if limit is not None:
            flagged = flagged[:limit]

        self.stdout.write(
            f"ℹ️ {len(flagged)}/{len(assigned)} блок(ів) позначено для Gemini vision OCR."
        )

        corrected = 0
        for preview, item in flagged:
            page_num = _page_for_line(line_boundaries, preview["start_line"])
            png_path = png_files.get(page_num)
            if png_path is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠️ Немає зображення для сторінки {page_num} -- пропускаю блок."
                    )
                )
                continue

            try:
                result = client.generate_from_image(
                    png_path,
                    _vision_ocr_prompt(preview["text"]),
                    prompt_version=VISION_OCR_PROMPT_VERSION,
                )
            except GeminiBudgetExceeded:
                self.stdout.write(
                    self.style.WARNING(
                        "⚠️ Вичерпано денний ліміт Gemini -- зупиняюсь, решта блоків "
                        "залишається з оригінальним OCR-текстом."
                    )
                )
                break
            except Exception as e:  # noqa: BLE001 -- surface but don't kill the whole run
                self.stdout.write(
                    self.style.WARNING(f"⚠️ Gemini-помилка на сторінці {page_num}: {e} -- пропускаю.")
                )
                continue

            preview["text"] = result.strip()
            corrected += 1

        self.stdout.write(f"✅ Виправлено {corrected} блок(ів) через Gemini vision.")
