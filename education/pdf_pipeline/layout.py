"""Етап 4: розмітка сторінки — що є колонтитулом, номером сторінки, а що текстом.

Колонтитул («2. Цифри. Десятковий запис натуральних чисел   7») друкується
на кожній сторінці. Якщо лишити його в тексті, він вклинюється посеред
вправ і плутає структурний парсер. Тому:

* рядки у верхній/нижній смузі сторінки позначаються зоною ``header``/``footer``
  і **не потрапляють** у ``body_lines``;
* номер сторінки з колонтитулу стає ``book_page`` (а не текстом);
* назва з колонтитулу зберігається **один раз** на документ
  (``collect_running_headers``) — зі списком сторінок, де вона була.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from .datatypes import Line, PageOcr
from .ocr import words_to_lines

HEADER_BAND = 0.11      # верхні 11% висоти сторінки — смуга колонтитула
FOOTER_BAND = 0.06      # нижні 6% — смуга нижнього колонтитула / номера
MAX_BOOK_PAGE = 999
SAME_HEADER_SCORE = 90  # схожість (0–100), з якої дві назви колонтитула вважаються однією

_PAGE_NUMBER_RE = re.compile(r"^\d{1,3}$")
# OCR читає «§» як «5» або «S»: «51. Натуральні» → «§ 1. Натуральні». Лише для колонтитулів.
_PARAGRAPH_SIGN_RE = re.compile(r"^(?:5|S|\$)\s?(\d{1,2})\.\s")


# --------------------------------------------------------------------------- колонтитул одного рядка


def is_page_number(text: str) -> bool:
    """«7», «123» — так; «7.», «12)» , «0», «1000» — ні."""
    return bool(_PAGE_NUMBER_RE.match(text)) and 1 <= int(text) <= MAX_BOOK_PAGE


def fix_paragraph_sign(title: str) -> str:
    """Виправляє типову помилку OCR у колонтитулі: «51. Натуральні числа» → «§ 1. Натуральні числа»."""
    return _PARAGRAPH_SIGN_RE.sub(lambda m: f"§ {m.group(1)}. ", title, count=1)


def split_running_header(line: Line) -> tuple[str, int | None]:
    """Розділяє рядок колонтитула на (назва, номер сторінки).

    Номер стоїть або першим словом (ліва сторінка: «6 § 1. Натуральні числа»),
    або останнім (права: «2. Цифри. … чисел 7»). Якщо номера немає — None.
    """
    words = [w.text for w in line.words]
    number: int | None = None
    if len(words) > 1 and is_page_number(words[-1]):
        number = int(words.pop())
    elif len(words) > 1 and is_page_number(words[0]):
        number = int(words.pop(0))
    elif len(words) == 1 and is_page_number(words[0]):
        return "", int(words[0])
    return fix_paragraph_sign(" ".join(words).strip()), number


# --------------------------------------------------------------------------- розмітка сторінки


@dataclass
class PageLayout:
    """Розмічена сторінка."""

    pdf_page: int
    page_height: int
    header_lines: list[Line] = field(default_factory=list)
    body_lines: list[Line] = field(default_factory=list)
    footer_lines: list[Line] = field(default_factory=list)
    header_title: str = ""           # назва з колонтитула (без номера сторінки)
    detected_book_page: int | None = None   # номер, прочитаний на самій сторінці
    book_page: int | None = None     # остаточний номер (можливо, виведений із сусідів)

    @property
    def body_text(self) -> str:
        return "\n".join(line.text for line in self.body_lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pdf_page": self.pdf_page, "page_height": self.page_height,
            "header_lines": [ln.to_dict() for ln in self.header_lines],
            "body_lines": [ln.to_dict() for ln in self.body_lines],
            "footer_lines": [ln.to_dict() for ln in self.footer_lines],
            "header_title": self.header_title,
            "detected_book_page": self.detected_book_page, "book_page": self.book_page,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageLayout:
        return cls(
            pdf_page=data["pdf_page"], page_height=data["page_height"],
            header_lines=[Line.from_dict(x) for x in data.get("header_lines", [])],
            body_lines=[Line.from_dict(x) for x in data.get("body_lines", [])],
            footer_lines=[Line.from_dict(x) for x in data.get("footer_lines", [])],
            header_title=data.get("header_title", ""),
            detected_book_page=data.get("detected_book_page"), book_page=data.get("book_page"),
        )


def analyze_page(
    lines: Sequence[Line],
    pdf_page: int,
    page_height: int,
    header_band: float = HEADER_BAND,
    footer_band: float = FOOTER_BAND,
) -> PageLayout:
    """Розкладає рядки сторінки на колонтитул / тіло / нижній колонтитул.

    Верхня смуга: усе, що в ній, — колонтитул (назва + номер).
    Нижня смуга: колонтитулом вважаємо лише рядок-число (номер сторінки) —
    звичайний текст унизу сторінки (кінець вправи) лишаємо в тілі.
    """
    layout = PageLayout(pdf_page=pdf_page, page_height=page_height)
    top_limit = page_height * header_band
    bottom_limit = page_height * (1 - footer_band)

    for line in lines:
        if not line.words:
            continue
        center_y = line.bbox.center[1]
        if center_y < top_limit:
            line.zone = "header"
            layout.header_lines.append(line)
        elif center_y > bottom_limit and is_page_number(line.text.strip()):
            line.zone = "footer"
            layout.footer_lines.append(line)
        else:
            line.zone = "body"
            layout.body_lines.append(line)

    titles: list[str] = []
    for line in layout.header_lines:
        title, number = split_running_header(line)
        if title:
            titles.append(title)
        if number is not None and layout.detected_book_page is None:
            layout.detected_book_page = number
    for line in layout.footer_lines:
        if layout.detected_book_page is None:
            layout.detected_book_page = int(line.text.strip())

    layout.header_title = " ".join(titles)
    layout.book_page = layout.detected_book_page
    return layout


def layout_from_ocr(result: PageOcr, **kwargs: Any) -> PageLayout:
    """Зручна обгортка: PageOcr → рядки → PageLayout."""
    lines = words_to_lines(result.words, result.page.pdf_page)
    return analyze_page(lines, result.page.pdf_page, result.page.height, **kwargs)


# --------------------------------------------------------------------------- рівень документа


def infer_book_pages(detected: Mapping[int, int | None]) -> dict[int, int | None]:
    """Номер у книзі = номер у PDF + зсув. Зсув — найчастіший серед прочитаних номерів.

    Так виправляються сторінки, де OCR не прочитав номер або прочитав неправильно
    (3 ↔ 8): номер, що не збігається з загальним зсувом, замінюється обчисленим.
    """
    offsets = Counter(book - pdf for pdf, book in detected.items() if book is not None)
    if not offsets:
        return dict(detected)
    offset, votes = offsets.most_common(1)[0]
    if votes < 2 and len(detected) > 2:      # один-єдиний номер — замало, щоб узагальнювати
        return dict(detected)
    return {pdf: pdf + offset for pdf in detected}


@dataclass
class RunningHeader:
    """Назва з колонтитула, збережена один раз, + на яких сторінках вона була."""

    title: str
    pages: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "pages": list(self.pages)}


def collect_running_headers(layouts: Iterable[PageLayout]) -> list[RunningHeader]:
    """Унікальні назви колонтитулів у порядку появи.

    OCR може трохи по-різному прочитати ту саму назву на різних сторінках —
    схожі (≥ SAME_HEADER_SCORE) об'єднуємо; канонічною стає найчастіша версія.
    """
    groups: list[tuple[Counter[str], list[int]]] = []
    for layout in layouts:
        title = layout.header_title.strip()
        if not title:
            continue
        for variants, pages in groups:
            best = variants.most_common(1)[0][0]
            if fuzz.ratio(title, best) >= SAME_HEADER_SCORE:
                variants[title] += 1
                pages.append(layout.pdf_page)
                break
        else:
            groups.append((Counter({title: 1}), [layout.pdf_page]))
    return [RunningHeader(variants.most_common(1)[0][0], pages) for variants, pages in groups]


def analyze_document(results: Sequence[PageOcr], **kwargs: Any) -> tuple[list[PageLayout], list[RunningHeader]]:
    """Розмічає всі сторінки, уточнює номери сторінок і збирає колонтитули."""
    layouts = [layout_from_ocr(r, **kwargs) for r in results]
    fixed = infer_book_pages({lay.pdf_page: lay.detected_book_page for lay in layouts})
    for lay in layouts:
        lay.book_page = fixed[lay.pdf_page]
    return layouts, collect_running_headers(layouts)
