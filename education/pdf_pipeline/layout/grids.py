"""Сітки підпунктів: «1) … 4) … 7)» у кілька колонок.

Підручник друкує підпункти вправи колонками:

    1) 238 + 435;    4) 2000 − 546;   7) 98 · 34;
    2) 4385 + 2697;  5) 3400 − 896;   8) 645 · 36.
    3) 843 − 457;    6) 23 · 46;

OCR читає по рядках (1, 4, 7, 2, 5, 8, …). Тут ми знаходимо маркери ``N)``,
визначаємо колонки за X-координатою і читаємо у правильному порядку.
Номер маркера, який OCR зіпсував (``9)`` замість ``5)``, ``17)`` замість ``7)``),
відновлюємо за позицією в сітці й позначаємо ``ocr_fixed``.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from ..datatypes import BBox, Line, Word

# Маркер: 1–2 цифри або одна літера + «)». Після дужки може бути приклеєний текст («1)238»).
_MARKER_RE = re.compile(r"^(\d{1,2}|[а-яіїєґa-z])\)(.*)$", re.IGNORECASE)
# Літери, які OCR видає замість цифр у маркерах.
_LETTER_AS_DIGIT = {"б": "6", "о": "0", "з": "3", "l": "1", "i": "1", "s": "5"}
COLUMN_GAP = 40   # px оригінальної картинки: маркери ближче — одна колонка


@dataclass
class Cell:
    """Один підпункт: маркер і слова після нього до наступного маркера."""

    raw_label: str            # як прочитав OCR: "9", "б", "17"
    words: list[Word]
    row: int                  # номер рядка всередині сітки
    x: int                    # лівий край маркера
    col: int = 0
    label: str = ""           # остаточний номер ("5")
    ocr_fixed: bool = False   # номер виправлено за позицією

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words).strip()

    @property
    def bbox(self) -> BBox | None:
        return BBox.union_all(w.bbox for w in self.words) if self.words else None


@dataclass
class Grid:
    """Блок послідовних рядків із підпунктами."""

    line_indices: list[int]                 # які рядки body_lines його утворюють
    cells: list[Cell] = field(default_factory=list)   # у правильному порядку читання
    order: str = "column"                   # "column" (по колонках) або "row" (по рядках)
    needs_review: bool = False              # порядок номерів так і не зійшовся

    @property
    def n_columns(self) -> int:
        return max((c.col for c in self.cells), default=-1) + 1


def _split_marker(word: Word) -> tuple[str, Word | None] | None:
    """Якщо слово — маркер, повертає (мітка, приклеєний текст як окреме слово або None)."""
    m = _MARKER_RE.match(word.text)
    if not m:
        return None
    rest = m.group(2)
    glued = Word(rest, word.bbox, word.conf, word.block_no, word.par_no, word.line_no, word.word_no) if rest else None
    return m.group(1).lower(), glued


def split_cells(line: Line, row: int) -> tuple[list[Word], list[Cell]]:
    """Ділить рядок на (слова до першого маркера, клітинки).

    Маркер рахується лише на початку рядка або після слова, що закінчується «;»,
    «,» чи «:» — інакше «(рис. 1) суми» перетворилось би на підпункт.
    """
    prefix: list[Word] = []
    cells: list[Cell] = []
    prev: Word | None = None
    for word in line.words:
        found = _split_marker(word)
        at_boundary = prev is None or prev.text.endswith((";", ",", ":"))
        if found and at_boundary:
            label, glued = found
            cells.append(Cell(raw_label=label, words=[glued] if glued else [], row=row, x=word.bbox.x0))
        elif cells:
            cells[-1].words.append(word)
        else:
            prefix.append(word)
        prev = word
    return prefix, cells


def _assign_columns(cells: list[Cell], gap: int) -> None:
    """Кластеризує X маркерів: відсортовані X, новий кластер, якщо розрив > gap."""
    xs = sorted({c.x for c in cells})
    column_of: dict[int, int] = {}
    col = 0
    for i, x in enumerate(xs):
        if i and x - xs[i - 1] > gap:
            col += 1
        column_of[x] = col
    for c in cells:
        c.col = column_of[c.x]


def _numeric(label: str) -> int | None:
    label = _LETTER_AS_DIGIT.get(label, label)
    return int(label) if label.isdigit() else None


def _score(order: Sequence[Cell], start: int) -> int:
    """Скільки маркерів збігаються з очікуваною послідовністю start, start+1, …"""
    return sum(1 for i, c in enumerate(order) if _numeric(c.raw_label) == start + i)


def read_grid(lines: Sequence[Line], line_indices: Sequence[int], gap: int = COLUMN_GAP) -> Grid:
    """Збирає клітинки з рядків, визначає колонки й порядок, відновлює номери."""
    cells: list[Cell] = []
    for row, line in enumerate(lines):
        cells.extend(split_cells(line, row)[1])
    grid = Grid(line_indices=list(line_indices))
    if not cells:
        return grid
    _assign_columns(cells, gap)

    by_column = sorted(cells, key=lambda c: (c.col, c.row))
    by_row = sorted(cells, key=lambda c: (c.row, c.col))

    numeric = [n for c in cells if (n := _numeric(c.raw_label)) is not None]
    letters = len(cells) - len(numeric)
    if letters > len(numeric):
        # Літерний список (а), б), в)) — номери не відновлюємо, лише порядок колонок.
        grid.cells, grid.order = by_column, "column"
        for c in grid.cells:
            c.label = c.raw_label
        return grid

    start = min(numeric) if numeric else 1
    start = 1 if start > 1 and _score(by_column, 1) >= _score(by_column, start) else start
    col_score, row_score = _score(by_column, start), _score(by_row, start)
    grid.order = "column" if col_score >= row_score else "row"
    grid.cells = by_column if grid.order == "column" else by_row

    for i, cell in enumerate(grid.cells):
        expected = start + i
        cell.label = str(expected)
        cell.ocr_fixed = _numeric(cell.raw_label) != expected
    # Якщо більше половини номерів довелося «вгадувати» — сітку краще перевірити людині.
    grid.needs_review = sum(c.ocr_fixed for c in grid.cells) * 2 > len(grid.cells)
    return grid


def _starts_with_marker(line: Line) -> bool:
    return bool(line.words) and _split_marker(line.words[0]) is not None


def find_grids(lines: Sequence[Line], gap: int = COLUMN_GAP) -> list[Grid]:
    """Знаходить сітки в рядках тіла сторінки.

    Сітка — це підряд рядки, що починаються з маркера, серед яких хоча б один
    містить ≥ 2 маркери (інакше це звичайний нумерований список в одну колонку —
    його теж повертаємо як сітку з 1 колонкою, якщо рядків ≥ 2).
    """
    grids: list[Grid] = []
    i = 0
    while i < len(lines):
        if not _starts_with_marker(lines[i]):
            i += 1
            continue
        j = i
        while j < len(lines) and _starts_with_marker(lines[j]):
            j += 1
        run = list(range(i, j))
        multi = any(len(split_cells(lines[k], 0)[1]) >= 2 for k in run)
        if multi or len(run) >= 2:
            grids.append(read_grid([lines[k] for k in run], run, gap))
        i = j
    return grids
