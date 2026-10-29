"""Потік рядків сторінки і звірка заголовків зі змістом книги.

Винесено зі ``structure.py`` (BE-S11): усе, що перетворює розмічені сторінки (``PageLayout``)
на потік рядків для автомата (``PageLine``, ``iter_body_lines``) і оцінює, наскільки рядок
схожий на заголовок § / пункту зі змісту (``_title_score`` і сусідні). Сам автомат — у
``parser.py``.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from rapidfuzz import fuzz

from ..datatypes import Line, SourceRef
from ..layout import PageLayout, split_running_header
from ..profiles.base import normalize_marker_text

TITLE_MATCH = 85          # схожість заголовка на сторінці з назвою у змісті (0–100)
PARAGRAPH_LOOKAHEAD = 3     # скільки § уперед від поточного ми готові «перескочити» через зіпсований номер

# Номер у заголовку §, як його бачить OCR: «§ 1.», «9 1.», «51.», «S 1.»
_PARAGRAPH_PREFIX_RE = re.compile(r"^\W*(?:§|5|9|S|\$)?\s*(?P<num>\d{1,3})\s*\.\s*")
_ITEM_PREFIX_RE = re.compile(r"^\W*(?P<num>\d{1,2})\s*\.\s*")
_CAPTION_RE = re.compile(r"^(?:Рис|Мал|Puc)\.?\s*\d+", re.IGNORECASE)
_HEADING_SIGN_RE = re.compile(r"^§\s?\d{1,2}\.\s*\S")     # лише справжній знак «§»
# Сміття перед заголовком §: «side § 16. КОЛО І КРУГ», «All § 4. РОЗКЛАДАННЯ»
_HEADING_JUNK_RE = re.compile(r"^[A-Za-zА-Яа-яІіЇїЄє]{1,8}\s+(?=\W?[§5S$9]?\s*\d{1,3}\s*\.)")


# --------------------------------------------------------------------------- допоміжне


@dataclass(frozen=True)
class ParseIssue:
    """Місце, яке парсер не зміг впевнено розібрати."""

    code: str
    message: str
    pdf_page: int
    text: str = ""

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "pdf_page": self.pdf_page, "text": self.text}


@dataclass
class PageLine:
    """Рядок разом із його сторінкою (потік рядків усієї книги)."""

    line: Line
    layout: PageLayout

    @property
    def text(self) -> str:
        return self.line.text.strip()

    @property
    def key(self) -> tuple[int, int]:
        return (self.layout.pdf_page, self.line.line_id)

    def source(self) -> SourceRef:
        return SourceRef(pdf_page=self.layout.pdf_page, book_page=self.layout.book_page,
                         bbox=self.line.bbox, line_ids=(self.line.line_id,))


def iter_body_lines(layouts: Iterable[PageLayout], skip_pages: Iterable[int] = ()) -> Iterator[PageLine]:
    """Рядки тіла всіх сторінок по порядку (колонтитули вже прибрані в layout)."""
    skip = set(skip_pages)
    for layout in sorted(layouts, key=lambda lay: lay.pdf_page):
        if layout.pdf_page in skip:
            continue
        # Перша сторінка § без колонтитула: «§ 5. Десяткові дроби» стоїть у верхній смузі й без номера сторінки
        # в тому ж рядку — це заголовок, а не колонтитул (у справжнього колонтитула номер у цьому ж рядку).
        for line in layout.header_lines:
            if line.words and _HEADING_SIGN_RE.match(line.text.strip()) and split_running_header(line)[1] is None:
                yield PageLine(line, layout)
        for line in layout.body_lines:
            if line.words:
                yield PageLine(line, layout)


def _title_score(text: str, title: str) -> float:
    return fuzz.ratio(normalize_marker_text(text), normalize_marker_text(title))


def _title_prefix_score(text: str, title: str) -> float:
    """Як _title_score, але рядок може бути лише початком назви (заголовок § перенесено на кілька рядків)."""
    a, b = normalize_marker_text(text), normalize_marker_text(title)
    full = fuzz.ratio(a, b)
    if len(a) >= 8 and len(a) < len(b):
        return max(full, fuzz.ratio(a, b[:len(a)]))
    return full


def _first_words_score(text: str, title: str, words: int = 2) -> float:
    """Схожість перших слів: хвіст заголовка OCR псує найчастіше, початок — рідше."""
    a, b = normalize_marker_text(text).split()[:words], normalize_marker_text(title).split()[:words]
    return fuzz.ratio(" ".join(a), " ".join(b)) if len(a) == words else 0.0


def _extend_bbox(source: SourceRef | None, line: PageLine) -> SourceRef:
    """Розширює SourceRef вузла ще одним рядком тієї ж сторінки (інші сторінки — лише line_ids)."""
    if source is None:
        return line.source()
    if source.pdf_page != line.layout.pdf_page or source.bbox is None:
        return source
    return SourceRef(source.pdf_page, source.book_page, source.bbox.union(line.line.bbox),
                     source.line_ids + (line.line.line_id,))
