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

from ..datatypes import BBox, Line, PageOcr
from ..ocr import words_to_lines
from .grids import Grid, find_grids

HEADER_BAND = 0.11      # верхні 11% висоти сторінки — смуга колонтитула
FOOTER_BAND = 0.06      # нижні 6% — смуга нижнього колонтитула / номера
MAX_BOOK_PAGE = 999
SAME_HEADER_SCORE = 90  # схожість (0–100), з якої дві назви колонтитула вважаються однією

NOISE_MAX_LEN = 2       # «сміття» від іконок: коротке слово...
NOISE_MAX_CONF = 40     # ...з низькою впевненістю, на краю рядка
BOXED_MIN_WORDS = 5     # стільки слів з літерами в рамці → текстова рамка, менше → рисунок
_CAPTION_RE = re.compile(r"^Рис\.?\s*(\d+)", re.IGNORECASE)

_PAGE_NUMBER_RE = re.compile(r"^\d{1,3}$")
# OCR читає «§» як «5», «9», «S» або «$»: «51. Натуральні» / «9 1. Натуральні» → «§ 1. Натуральні».
# Лише для колонтитулів — у звичайному тексті «51.» може бути номером вправи.
_PARAGRAPH_SIGN_RE = re.compile(r"^(?:5|9|S|\$)\s?(\d{1,2})\.\s")


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


# --------------------------------------------------------------------------- шум і рамки


def strip_edge_noise(line: Line, max_len: int = NOISE_MAX_LEN, max_conf: float = NOISE_MAX_CONF) -> Line:
    """Прибирає короткі слова з низькою впевненістю на краях рядка.

    Іконка Мудрої Сови перед заголовком читається як «2» з conf 21 →
    «2 Задача від Мудрої Сови». Такі слова майже завжди сміття від картинок.
    """
    words = list(line.words)

    def is_noise(w) -> bool:
        return len(w.text) <= max_len and w.conf < max_conf

    while words and is_noise(words[0]):
        words.pop(0)
    while words and is_noise(words[-1]):
        words.pop()
    line.words = words
    return line


@dataclass
class Region:
    """Рамка на сторінці: ``boxed`` (текст у рамці) або ``figure`` (рисунок/таблиця)."""

    kind: str
    bbox: BBox
    caption: str = ""        # «Рис. 1», якщо знайдено підпис

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "bbox": self.bbox.to_dict(), "caption": self.caption}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Region:
        return cls(data["kind"], BBox.from_dict(data["bbox"]), data.get("caption", ""))


def _inside(line: Line, box: BBox) -> bool:
    cx, cy = line.bbox.center
    return box.x0 <= cx <= box.x1 and box.y0 <= cy <= box.y1


def _letter_words(lines: Sequence[Line]) -> int:
    return sum(1 for ln in lines for w in ln.words if sum(ch.isalpha() for ch in w.text) >= 2)


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
    regions: list[Region] = field(default_factory=list)
    figure_lines: list[Line] = field(default_factory=list)   # «текст» усередині рисунків — не в body

    @property
    def body_text(self) -> str:
        return "\n".join(line.text for line in self.body_lines)

    def grids(self) -> list[Grid]:
        """Сітки підпунктів серед рядків тіла (рахуються щоразу — це дешево)."""
        return find_grids(self.body_lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pdf_page": self.pdf_page, "page_height": self.page_height,
            "header_lines": [ln.to_dict() for ln in self.header_lines],
            "body_lines": [ln.to_dict() for ln in self.body_lines],
            "footer_lines": [ln.to_dict() for ln in self.footer_lines],
            "header_title": self.header_title,
            "detected_book_page": self.detected_book_page, "book_page": self.book_page,
            "regions": [r.to_dict() for r in self.regions],
            "figure_lines": [ln.to_dict() for ln in self.figure_lines],
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
            regions=[Region.from_dict(x) for x in data.get("regions", [])],
            figure_lines=[Line.from_dict(x) for x in data.get("figure_lines", [])],
        )


def analyze_page(
    lines: Sequence[Line],
    pdf_page: int,
    page_height: int,
    header_band: float = HEADER_BAND,
    footer_band: float = FOOTER_BAND,
    frames: Sequence[BBox] = (),
) -> PageLayout:
    """Розкладає рядки сторінки на колонтитул / тіло / нижній колонтитул.

    Верхня смуга: усе, що в ній, — колонтитул (назва + номер).
    Нижня смуга: колонтитулом вважаємо лише рядок-число (номер сторінки) —
    звичайний текст унизу сторінки (кінець вправи) лишаємо в тілі.
    ``frames`` — рамки з regions.detect_frames: рядки в рамці-рисунку прибираються
    з тіла (це числа з таблиці, а не текст), у текстовій рамці — позначаються ``boxed``.
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
            layout.body_lines.append(strip_edge_noise(line))
    layout.body_lines = [ln for ln in layout.body_lines if ln.words]

    for frame in frames:
        if frame.center[1] < top_limit:          # декор у колонтитулі
            continue
        inside = [ln for ln in layout.body_lines if _inside(ln, frame)]
        kind = "boxed" if _letter_words(inside) >= BOXED_MIN_WORDS else "figure"
        layout.regions.append(Region(kind, frame))
        for ln in inside:
            ln.zone = kind
        if kind == "figure":
            layout.figure_lines.extend(inside)
            layout.body_lines = [ln for ln in layout.body_lines if ln not in inside]
    _attach_captions(layout)

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


def _attach_captions(layout: PageLayout) -> None:
    """Підпис «Рис. N» прив'язується до найближчого за вертикаллю рисунка."""
    figures = [r for r in layout.regions if r.kind == "figure"]
    for line in layout.body_lines:
        m = _CAPTION_RE.match(line.text)
        if not m or not figures:
            continue
        cy = line.bbox.center[1]
        nearest = min(figures, key=lambda r: min(abs(cy - r.bbox.y0), abs(cy - r.bbox.y1)))
        nearest.caption = f"Рис. {m.group(1)}"


def layout_from_ocr(result: PageOcr, detect_regions: bool = True, **kwargs: Any) -> PageLayout:
    """Зручна обгортка: PageOcr → рядки → PageLayout (рамки шукаються на картинці сторінки)."""
    lines = words_to_lines(result.words, result.page.pdf_page)
    if detect_regions and "frames" not in kwargs and result.page.path.exists():
        from ..ingest.preprocess import load_image
        from .regions import detect_frames
        kwargs["frames"] = detect_frames(load_image(result.page.path))
    return analyze_page(lines, result.page.pdf_page, result.page.height, **kwargs)


# --------------------------------------------------------------------------- рівень документа


def infer_book_pages(detected: Mapping[int, int | None], window: int = 8) -> dict[int, int | None]:
    """Номер у книзі = номер у PDF + зсув. Зсув — найчастіший серед **сусідніх** сторінок.

    Так виправляються сторінки, де OCR не прочитав номер або прочитав неправильно
    (3 ↔ 8). Зсув рахуємо в «вікні» ±window сторінок, а не по всій книзі: у
    Тарасенковій на початку зсув 0, а в кінці 9 (десь посередині вставлені
    ненумеровані сторінки) — один спільний зсув зламав би половину книги.
    """
    pages = sorted(detected)
    result: dict[int, int | None] = {}
    for pdf in pages:
        offsets = Counter(
            book - other for other in pages
            if abs(other - pdf) <= window and (book := detected[other]) is not None
        )
        if not offsets:
            result[pdf] = detected[pdf]
            continue
        offset, votes = offsets.most_common(1)[0]
        own = detected[pdf]
        # Один-єдиний голос (лише сама сторінка) — довіряємо прочитаному, нічого не вигадуємо.
        result[pdf] = own if votes < 2 and own is not None else (pdf + offset if votes >= 2 else own)
    return result


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
