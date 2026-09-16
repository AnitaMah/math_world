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
per the refactor plan). Later steps (16-19) add exercise, oral_exercise,
wise_owl, and history_aside the same way.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

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
