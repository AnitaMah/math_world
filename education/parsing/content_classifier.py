"""
Step 15+ of the refactor plan: classifiers that find structured content
blocks (theory, exercises, asides) inside a lesson's raw OCR'd text, one
block type at a time -- see refactor plan Section 3, "Content extraction:
build the pipeline one block type at a time".

This module is deliberately dry-run-first: every classifier here just
*finds and returns* candidate blocks from raw text. Nothing writes to the
database. The management command (Step 20's --dry-run flag) is what
prints these for review, and only once they've been checked by hand does
anything get imported for real (Step 22) -- the same discipline used for
the Розділ/TOC import earlier in this project after the "was never
actually run against the real DB" bug.

Step 15 implements exactly one block type: "review_exercise" ("Вправи
для повторення" -- the clearest, least ambiguous marker in the book,
per the refactor plan). Step 16 adds "exercise" (the plain "Вправи"
list, capturing each item's difficulty marker). Later steps (17-19) add
oral_exercise, wise_owl, and history_aside the same way.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# The exact marker that opens a "review exercises" block. Confirmed
# against real OCR'd text (review/section_1_text/combined.txt, §1 of the
# grade-5 Merzlyak book) -- appears verbatim, on its own line.
REVIEW_EXERCISE_MARKER_RE = re.compile(r"^Вправи для повторення\s*$", re.IGNORECASE)

# Markers that end a review_exercise block if they show up first --
# i.e. any other named section starting, or a new lesson beginning.
# Matches what's used elsewhere in the pipeline: "Задача від Мудрої
# Сови" (wise_owl), "Коли зроблено уроки" (history_aside), a bare
# "Вправи" heading (not "для повторення"), "Розв'язуємо усно"
# (oral_exercise), or a new numbered lesson title.
#
# Uses .search (not .match/^) because OCR frequently prepends garbage
# before a short marker line -- e.g. a small icon before "Задача від
# Мудрої Сови" comes out as "зб Задача від Мудрої Сови ох |" in real
# OCR'd text (confirmed in review/section_1_text/combined.txt). A
# strict line-start match would silently miss real block boundaries.
BLOCK_END_MARKERS_RE = [
    re.compile(r"Задача від Мудрої Сови", re.IGNORECASE),
    re.compile(r"Коли зроблено уроки", re.IGNORECASE),
    re.compile(r"^\W*Вправи\W*$", re.IGNORECASE),
    re.compile(r"Розв'язуємо усно", re.IGNORECASE),
]

# A new numbered exercise inside the block, e.g. "12. Обчисліть:" --
# used only to confirm a captured block actually looks like a numbered
# exercise list, not a false-positive marker match.
NUMBERED_LINE_RE = re.compile(r"^\d+[\".]?\s*[А-ЯІЇЄA-Z]")


@dataclass
class ReviewExerciseBlock:
    start_line: int          # 0-indexed line number in the input, for review
    end_line: int
    text: str                # raw captured text, unedited -- OCR mistakes and all


def find_review_exercise_blocks(raw_text: str) -> List[ReviewExerciseBlock]:
    """
    Scans raw OCR'd lesson text (e.g. a whole section's combined pages)
    for "Вправи для повторення" blocks and returns each one's raw
    captured text plus its line range, for manual review before anything
    is imported.

    Deliberately conservative: if a block doesn't contain at least one
    numbered line, it's dropped rather than guessed at -- a missed block
    is safer than a wrong one at this dry-run stage.
    """
    lines = raw_text.splitlines()
    blocks: List[ReviewExerciseBlock] = []

    i = 0
    while i < len(lines):
        if REVIEW_EXERCISE_MARKER_RE.match(lines[i].strip()):
            start = i
            i += 1
            captured: List[str] = []
            while i < len(lines):
                stripped = lines[i].strip()
                if any(rx.search(stripped) for rx in BLOCK_END_MARKERS_RE):
                    break
                # A blank line doesn't necessarily end the block (OCR'd
                # exercise lists have blank lines between items), so we
                # only stop on an explicit marker above, or end of text.
                captured.append(lines[i])
                i += 1

            block_text = "\n".join(captured).strip()
            if any(NUMBERED_LINE_RE.match(l.strip()) for l in captured):
                blocks.append(
                    ReviewExerciseBlock(start_line=start, end_line=i, text=block_text)
                )
            continue
        i += 1

    return blocks


# ---------------------------------------------------------------------
# Step 16: "exercise" -- the plain "Вправи" list (not "для повторення"),
# capturing each numbered item's difficulty marker if present.
# ---------------------------------------------------------------------

# A bare "Вправи" heading, not "Вправи для повторення" -- the negative
# case is automatic here since this only matches when nothing else is on
# the line.
EXERCISE_MARKER_RE = re.compile(r"^\W*Вправи\W*$", re.IGNORECASE)

EXERCISE_BLOCK_END_MARKERS_RE = [
    re.compile(r"Вправи для повторення", re.IGNORECASE),
    re.compile(r"Задача від Мудрої Сови", re.IGNORECASE),
    re.compile(r"Коли зроблено уроки", re.IGNORECASE),
    re.compile(r"Розв'язуємо усно", re.IGNORECASE),
]

# A numbered exercise, optionally followed by a difficulty marker right
# after the period. The book uses a small superscript circle (°) to mark
# an easier/introductory exercise; OCR is inconsistent about it --
# observed in real text as a straight double-quote (") rather than a
# degree sign, and rendered *after* the period (e.g. `2." Якого числа...`),
# not before it. Other markers mentioned in the original diagnosis (··, *)
# haven't actually been observed in OCR'd text yet, so only the confirmed
# one is matched for now rather than guessing at the others' OCR renderings.
EXERCISE_ITEM_RE = re.compile(r'^(\d+)\.(["°]?)\s*(.*)$')

# How far an item number is allowed to jump from the previous one and
# still be trusted as a genuine new item. Real exercise lists in this
# book number sequentially with no gaps, so a small jump (e.g. a missed
# item) is plausible, but a huge one is almost always OCR digit confusion
# (observed in real text: "32." misread as "82.") rather than a real skip
# forward -- and if left unchecked, that inflated number becomes the new
# high-water mark and silently swallows every real item after it, since
# their genuinely smaller numbers never exceed it again. Capping the
# jump lets the very next real, small number resync as a new item
# instead of being folded into the misread one's text.
MAX_ITEM_NUMBER_JUMP = 5


@dataclass
class ExerciseItem:
    number: int
    difficulty: Optional[str]   # "basic" if a marker was found, else None (standard)
    text: str


@dataclass
class ExerciseBlock:
    start_line: int
    end_line: int
    items: List[ExerciseItem] = field(default_factory=list)


def find_exercise_blocks(raw_text: str) -> List[ExerciseBlock]:
    """
    Scans raw OCR'd lesson text for plain "Вправи" lists and splits each
    into individual numbered ExerciseItems, tagging a difficulty marker
    when present.

    Guards against a real false positive found while testing against
    actual OCR'd text: a running page header ("2. Цифри. Десятковий
    запис натуральних чисел 7") bleeds into the middle of an exercise
    list and looks exactly like a new numbered item. Since real exercise
    numbers only ever increase within one list, any "match" whose number
    doesn't exceed the highest one seen so far is treated as noise and
    folded into the current item's text instead of starting a new one --
    catches this class of bleed-through without hardcoding the specific
    noise text, which would only handle this one exact case.
    """
    lines = raw_text.splitlines()
    blocks: List[ExerciseBlock] = []

    i = 0
    while i < len(lines):
        if EXERCISE_MARKER_RE.match(lines[i].strip()):
            start = i
            i += 1
            items: List[ExerciseItem] = []
            current: Optional[ExerciseItem] = None
            max_number_seen = 0

            while i < len(lines):
                stripped = lines[i].strip()
                if any(rx.search(stripped) for rx in EXERCISE_BLOCK_END_MARKERS_RE):
                    break

                m = EXERCISE_ITEM_RE.match(stripped)
                number = int(m.group(1)) if m else None
                jump = number - max_number_seen if number is not None else None
                if m and (current is None or (0 < jump <= MAX_ITEM_NUMBER_JUMP)):
                    max_number_seen = number
                    marker = m.group(2)
                    current = ExerciseItem(
                        number=number,
                        difficulty="basic" if marker else None,
                        text=m.group(3).strip(),
                    )
                    items.append(current)
                elif stripped and current is not None:
                    current.text += "\n" + stripped
                # else: stray line before the first real item, or a
                # blank line -- dropped, not appended anywhere.
                i += 1

            if items:
                blocks.append(ExerciseBlock(start_line=start, end_line=i, items=items))
            continue
        i += 1

    return blocks


# ---------------------------------------------------------------------
# Step 17: "oral_exercise" -- the "Розв'язуємо усно" (mental-math warm-up)
# list. Confirmed against real OCR'd text (review/section_1_text/
# combined.txt, lines 44 and 197): a bare "Розв'язуємо усно" heading on
# its own line, followed by a plain numbered list ("1.", "2.", ...) with
# no difficulty markers -- unlike "exercise" (Step 16), this textbook
# never marks an oral warm-up item as easier/harder, so ExerciseItem's
# marker group isn't reused here; a simpler ExerciseItem-alike without a
# difficulty field is enough. Both real occurrences end at the next bare
# "Вправи" heading, but any of the other named-section markers are
# treated as an end too, in case a lesson has no "Вправи" list at all.
# ---------------------------------------------------------------------

ORAL_EXERCISE_MARKER_RE = re.compile(r"^Розв'язуємо усно\s*$", re.IGNORECASE)

ORAL_EXERCISE_BLOCK_END_MARKERS_RE = [
    re.compile(r"^\W*Вправи\W*$", re.IGNORECASE),
    re.compile(r"Вправи для повторення", re.IGNORECASE),
    re.compile(r"Задача від Мудрої Сови", re.IGNORECASE),
    re.compile(r"Коли зроблено уроки", re.IGNORECASE),
]

# A plain numbered item, no difficulty marker -- e.g. "1. Додайте:".
ORAL_EXERCISE_ITEM_RE = re.compile(r"^(\d+)\.\s*(.*)$")


@dataclass
class OralExerciseItem:
    number: int
    text: str


@dataclass
class OralExerciseBlock:
    start_line: int
    end_line: int
    items: List[OralExerciseItem] = field(default_factory=list)


def find_oral_exercise_blocks(raw_text: str) -> List[OralExerciseBlock]:
    """
    Scans raw OCR'd lesson text for "Розв'язуємо усно" blocks and splits
    each into individual numbered OralExerciseItems.

    Reuses the same increasing-number guard as find_exercise_blocks (see
    MAX_ITEM_NUMBER_JUMP): a running page header re-using a low number
    (the same class of OCR bleed-through documented there, e.g.
    "10 9 1. Натуральні числа") must not be mistaken for a new item, so
    any match whose number doesn't exceed the highest one seen so far is
    folded into the current item's text instead of starting a new one --
    and a wildly-inflated misread (e.g. "6." for a real "5.") isn't
    allowed to become the new high-water mark either, so real items right
    after it can still resync.
    """
    lines = raw_text.splitlines()
    blocks: List[OralExerciseBlock] = []

    i = 0
    while i < len(lines):
        if ORAL_EXERCISE_MARKER_RE.match(lines[i].strip()):
            start = i
            i += 1
            items: List[OralExerciseItem] = []
            current: Optional[OralExerciseItem] = None
            max_number_seen = 0

            while i < len(lines):
                stripped = lines[i].strip()
                if any(rx.search(stripped) for rx in ORAL_EXERCISE_BLOCK_END_MARKERS_RE):
                    break

                m = ORAL_EXERCISE_ITEM_RE.match(stripped)
                number = int(m.group(1)) if m else None
                jump = number - max_number_seen if number is not None else None
                if m and (current is None or (0 < jump <= MAX_ITEM_NUMBER_JUMP)):
                    max_number_seen = number
                    current = OralExerciseItem(number=number, text=m.group(2).strip())
                    items.append(current)
                elif stripped and current is not None:
                    current.text += "\n" + stripped
                # else: stray line before the first real item, or a
                # blank line -- dropped, not appended anywhere.
                i += 1

            if items:
                blocks.append(OralExerciseBlock(start_line=start, end_line=i, items=items))
            continue
        i += 1

    return blocks


# ---------------------------------------------------------------------
# Step 18: "wise_owl" -- the "Задача від Мудрої Сови" problem. Per the
# refactor plan, "usually exactly one per item, simplest to detect" --
# confirmed against two real occurrences in review/section_1_text/
# combined.txt (lines 115 and 347): the marker is followed by exactly
# one numbered problem (continuing the lesson's overall exercise
# numbering, e.g. "17." / "44." -- not its own 1-based count), ending at
# the very next blank line.
#
# Unlike find_review_exercise_blocks/find_exercise_blocks (which
# deliberately do NOT stop at a blank line, since those lists hold many
# items separated by blanks), a wise_owl block holds exactly one item --
# so the first blank line *after real content has started* reliably
# marks its end. This also sidesteps a genuine OCR hazard seen in the
# first real example: the block sits at the very end of one lesson,
# immediately followed by the next lesson's title bleeding in with no
# marker of its own ("2. Цифри. Десятковий запис натуральних чисел") --
# stopping at the first blank line means that bleed-through is never
# captured, without needing to special-case it.
#
# Uses .search (not .match/^) for the marker itself, same as
# BLOCK_END_MARKERS_RE above, since OCR frequently prepends garbage
# before it -- confirmed here as both "зб ... ох |" and "з»".
# ---------------------------------------------------------------------

WISE_OWL_MARKER_RE = re.compile(r"Задача від Мудрої Сови", re.IGNORECASE)

WISE_OWL_BLOCK_END_MARKERS_RE = [
    re.compile(r"Коли зроблено уроки", re.IGNORECASE),
    re.compile(r"Вправи для повторення", re.IGNORECASE),
    re.compile(r"^\W*Вправи\W*$", re.IGNORECASE),
    re.compile(r"Розв'язуємо усно", re.IGNORECASE),
]


@dataclass
class WiseOwlBlock:
    start_line: int          # 0-indexed line number in the input, for review
    end_line: int
    text: str                # raw captured text, unedited -- OCR mistakes and all


def find_wise_owl_blocks(raw_text: str) -> List[WiseOwlBlock]:
    """
    Scans raw OCR'd lesson text for "Задача від Мудрої Сови" blocks and
    returns each one's raw captured text plus its line range.

    Deliberately conservative like find_review_exercise_blocks: if a
    block doesn't contain at least one numbered line, it's dropped
    rather than guessed at -- a missed block is safer than a wrong one.
    """
    lines = raw_text.splitlines()
    blocks: List[WiseOwlBlock] = []

    i = 0
    while i < len(lines):
        if WISE_OWL_MARKER_RE.search(lines[i].strip()):
            start = i
            i += 1
            captured: List[str] = []
            started = False

            while i < len(lines):
                stripped = lines[i].strip()

                if not stripped:
                    # A blank line before any real content has been
                    # captured is just the gap between the marker and
                    # its problem (both real examples have one) -- skip
                    # it. Once content has started, a blank line is
                    # exactly what marks the end of this single item.
                    if started:
                        break
                    i += 1
                    continue

                if any(rx.search(stripped) for rx in WISE_OWL_BLOCK_END_MARKERS_RE):
                    break

                captured.append(lines[i])
                started = True
                i += 1

            block_text = "\n".join(captured).strip()
            if any(NUMBERED_LINE_RE.match(l.strip()) for l in captured):
                blocks.append(WiseOwlBlock(start_line=start, end_line=i, text=block_text))
            continue
        i += 1

    return blocks


# ---------------------------------------------------------------------
# Step 19: "history_aside" -- the "Коли зроблено уроки" historical box.
# Per the refactor plan, "hardest, spans a page-layout box; do this
# last" -- confirmed against the one real occurrence in
# review/section_1_text/combined.txt (lines 353-493): unlike every other
# block type here, this one is a genuine multi-paragraph essay (this
# example alone runs ~140 lines), with no blank-line or short-marker
# structure to lean on. It even contains an internal sub-heading of its
# own ("Як називають «числа-велетні»", line 473) and running-header
# bleed-through ("Як рахували в давнину 13", "їщ 9 1. Натуральні числа")
# scattered through it -- none of that is specially handled, since it's
# all just prose that becomes part of the captured text, same as any
# other line.
#
# What actually, reliably ends this block: the next real lesson heading
# ("3. Відрізок. Довжина відрізка", line 494). A direct check confirmed
# NUMBERED_LINE_RE (already used elsewhere to *confirm* real content)
# does not spuriously match anywhere else inside these ~140 lines, so it
# doubles as the end condition here -- the only line it matches between
# the marker and the real boundary is that boundary itself. The other
# known block markers are included too, for the (not yet observed in
# this fixture, but noted in the refactor plan Section 1.2) case of an
# item having a second, separate "Коли зроблено уроки" aside, or any
# other named block starting right after this one instead of a new
# lesson.
# ---------------------------------------------------------------------

HISTORY_ASIDE_MARKER_RE = re.compile(r"Коли зроблено уроки", re.IGNORECASE)

HISTORY_ASIDE_BLOCK_END_MARKERS_RE = [
    re.compile(r"Вправи для повторення", re.IGNORECASE),
    re.compile(r"^\W*Вправи\W*$", re.IGNORECASE),
    re.compile(r"Розв'язуємо усно", re.IGNORECASE),
    WISE_OWL_MARKER_RE,
    HISTORY_ASIDE_MARKER_RE,
]


@dataclass
class HistoryAsideBlock:
    start_line: int          # 0-indexed line number in the input, for review
    end_line: int
    text: str                # raw captured text, unedited -- OCR mistakes and all


def find_history_aside_blocks(raw_text: str) -> List[HistoryAsideBlock]:
    """
    Scans raw OCR'd lesson text for "Коли зроблено уроки" blocks and
    returns each one's raw captured text plus its line range.

    Unlike every other classifier in this module, does NOT require at
    least one numbered line to confirm real content -- the opposite is
    true here: a numbered line is exactly what signals the block has
    ended (see the module comment above). The conservative check instead
    is simply that some non-blank text was captured at all.
    """
    lines = raw_text.splitlines()
    blocks: List[HistoryAsideBlock] = []

    i = 0
    while i < len(lines):
        if HISTORY_ASIDE_MARKER_RE.search(lines[i].strip()):
            start = i
            i += 1
            captured: List[str] = []

            while i < len(lines):
                stripped = lines[i].strip()

                if stripped and NUMBERED_LINE_RE.match(stripped):
                    break
                if any(rx.search(stripped) for rx in HISTORY_ASIDE_BLOCK_END_MARKERS_RE):
                    break

                captured.append(lines[i])
                i += 1

            block_text = "\n".join(captured).strip()
            if block_text:
                blocks.append(HistoryAsideBlock(start_line=start, end_line=i, text=block_text))
            continue
        i += 1

    return blocks


def collect_content_block_previews(raw_text: str) -> List[dict]:
    """
    Step 20: runs every Step 15-19 classifier over the same raw OCR text
    and merges their output into one document-ordered list of "preview"
    dicts -- one per future ContentBlock row -- for import_curriculum
    --dry-run to print without touching the database.

    exercise/oral_exercise blocks group several numbered items under one
    marker, but ContentBlock is one row per item, so those blocks are
    expanded here into one preview per item instead of one preview per
    block.
    """
    previews: List[dict] = []

    for block in find_review_exercise_blocks(raw_text):
        previews.append(
            {
                "start_line": block.start_line,
                "block_type": "review_exercise",
                "difficulty": None,
                "text": block.text,
            }
        )

    for block in find_exercise_blocks(raw_text):
        for item in block.items:
            previews.append(
                {
                    "start_line": block.start_line,
                    "block_type": "exercise",
                    "difficulty": item.difficulty,
                    "text": item.text,
                }
            )

    for block in find_oral_exercise_blocks(raw_text):
        for item in block.items:
            previews.append(
                {
                    "start_line": block.start_line,
                    "block_type": "oral_exercise",
                    "difficulty": None,
                    "text": item.text,
                }
            )

    for block in find_wise_owl_blocks(raw_text):
        previews.append(
            {
                "start_line": block.start_line,
                "block_type": "wise_owl",
                "difficulty": None,
                "text": block.text,
            }
        )

    for block in find_history_aside_blocks(raw_text):
        previews.append(
            {
                "start_line": block.start_line,
                "block_type": "history_aside",
                "difficulty": None,
                "text": block.text,
            }
        )

    previews.sort(key=lambda p: p["start_line"])
    for order, preview in enumerate(previews):
        preview["order"] = order

    return previews

    return blocks
