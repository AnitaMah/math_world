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
"""
from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import ContentBlock, Item, Paragraph
from education.parsing.content_classifier import collect_content_block_previews


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


class Command(BaseCommand):
    help = (
        "Записує реальні ContentBlock з сирого OCR-тексту, зіставляючи кожен "
        "блок з відповідним пунктом (Item) за рядком його заголовка (Step 22)."
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
