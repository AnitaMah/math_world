"""Етап 0: інспекція PDF — що це за файл і як з нього діставати текст.

Визначає для кожної сторінки: є шрифти чи ні, скільки картинок, яка
роздільність скану (ppi), чи є текстовий шар і наскільки він якісний.
На основі цього класифікує весь документ (``PdfKind``).

Запуск з терміналу:
    python -m education.pdf_pipeline.pdf_inspect 5-klas-matematika-merzljak-2018-1-46.pdf
"""
from __future__ import annotations

import argparse
import hashlib
import re
import statistics
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import pymupdf

from .cache import save_json

LOW_RES_PPI = 120.0          # нижче — сторінка «низької роздільності»
FULL_PAGE_COVERAGE = 0.9     # картинка займає ≥90% сторінки → це скан
GLYPHLESS_FONT = "GlyphLessFont"  # шрифт невидимого OCR-шару (Tesseract, iLovePDF...)

_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_WORD_RE = re.compile(r"\w+")


# --------------------------------------------------------------------------- відкриття і хеш


def open_pdf(path: str | Path) -> pymupdf.Document:
    """Відкриває PDF із зрозумілою помилкою, якщо файлу немає."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF не знайдено: {path}")
    return pymupdf.open(path)


def pdf_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """SHA-256 файлу, читаючи блоками по 1 МБ (Тарасенкова важить 55 МБ)."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- якість тексту


def cyrillic_ratio(text: str) -> float:
    """Частка кириличних літер серед усіх літер (0..1). Без літер — 0."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    cyr = sum(1 for ch in letters if _CYRILLIC_RE.match(ch))
    return cyr / len(letters)


def mixed_script_words(text: str) -> list[str]:
    """Слова, де змішані кирилиця і латиниця (`cBoei`, `Mep3nak`) — ознака поганого OCR."""
    return [w for w in _WORD_RE.findall(text) if _CYRILLIC_RE.search(w) and _LATIN_RE.search(w)]


def text_layer_quality(text: str) -> float:
    """Груба оцінка якості українського текстового шару, 0..1.

    = частка кирилиці × (1 − частка «мішаних» слів).
    Чистий український текст ≈ 1; латинські двійники (`Bech`, `Ha`) і мішані
    слова знижують оцінку; порожній текст = 0.
    """
    words = [w for w in _WORD_RE.findall(text) if any(ch.isalpha() for ch in w)]
    if not words:
        return 0.0
    mixed_share = len(mixed_script_words(text)) / len(words)
    return cyrillic_ratio(text) * (1.0 - mixed_share)


# --------------------------------------------------------------------------- одна сторінка


@dataclass(frozen=True)
class PageInspection:
    """Факти про одну сторінку PDF."""

    pdf_page: int                 # з 1
    width_pt: float
    height_pt: float
    fonts: tuple[str, ...]
    n_images: int
    max_ppi: float | None         # роздільність найбільшої картинки; None — картинок немає
    image_coverage: float         # частка площі сторінки під найбільшою картинкою, 0..1
    text_chars: int               # скільки непробільних символів у текстовому шарі
    text_quality: float           # text_layer_quality(), 0..1

    @property
    def has_glyphless(self) -> bool:
        return GLYPHLESS_FONT in self.fonts

    @property
    def is_scanned(self) -> bool:
        """Сторінка — це одна велика картинка (скан)."""
        return self.image_coverage >= FULL_PAGE_COVERAGE

    @property
    def category(self) -> str:
        """Тип сторінки: scan_only / scan_with_ocr_layer / born_digital / empty / mixed."""
        if self.is_scanned and self.text_chars == 0:
            return "scan_only"
        if self.is_scanned and self.has_glyphless:
            return "scan_with_ocr_layer"
        if self.fonts and self.text_chars > 0 and not self.has_glyphless:
            return "born_digital"
        if self.n_images == 0 and self.text_chars == 0:
            return "empty"
        return "mixed"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["fonts"] = list(self.fonts)
        data["category"] = self.category
        return data


def inspect_page(page: pymupdf.Page, pdf_page: int) -> PageInspection:
    """Збирає факти про сторінку (pdf_page — її номер з 1, для звітів)."""
    rect = page.rect
    page_area = rect.width * rect.height or 1.0

    fonts = tuple(sorted({f[3] for f in page.get_fonts()}))
    images = page.get_images(full=True)

    max_ppi: float | None = None
    coverage = 0.0
    # get_image_info() без hashes: один прохід по сторінці. get_image_rects(xref) рахує
    # хеші всіх картинок на кожен виклик — на Windows це хвилини на 46 сторінок.
    for info in page.get_image_info():
        shown = pymupdf.Rect(info["bbox"])           # де картинка намальована на сторінці
        if shown.width <= 0 or not info.get("width"):
            continue
        ppi = info["width"] / (shown.width / 72.0)   # 72 pt = 1 дюйм
        area_share = (shown.width * shown.height) / page_area
        if area_share > coverage:
            coverage, max_ppi = area_share, ppi

    text = page.get_text()
    return PageInspection(
        pdf_page=pdf_page,
        width_pt=round(rect.width, 2),
        height_pt=round(rect.height, 2),
        fonts=fonts,
        n_images=len(images),
        max_ppi=round(max_ppi, 1) if max_ppi else None,
        image_coverage=round(min(coverage, 1.0), 3),
        text_chars=sum(1 for ch in text if not ch.isspace()),
        text_quality=round(text_layer_quality(text), 3),
    )


# --------------------------------------------------------------------------- весь документ


class PdfKind(str, Enum):
    """Тип документа загалом (str — щоб красиво лягав у JSON)."""

    BORN_DIGITAL = "born_digital"                 # текст справжній — OCR не потрібен
    SCAN_WITH_OCR_LAYER = "scan_with_ocr_layer"   # скан + чужий невидимий OCR (Мерзляк)
    SCAN_ONLY = "scan_only"                       # лише картинки (Тарасенкова)
    MIXED = "mixed"                               # сторінки різних типів
    EMPTY = "empty"                               # нічого немає


def classify_pdf(pages: Sequence[PageInspection]) -> PdfKind:
    """Тип документа: якщо всі непорожні сторінки одного типу — він, інакше MIXED."""
    categories = {p.category for p in pages if p.category != "empty"}
    if not categories:
        return PdfKind.EMPTY
    if len(categories) == 1:
        return PdfKind(categories.pop())
    return PdfKind.MIXED


@dataclass(frozen=True)
class PdfInspection:
    """Результат інспекції цілого PDF."""

    path: str
    sha256: str
    page_count: int
    kind: PdfKind
    median_ppi: float | None
    low_res_pages: tuple[int, ...]
    pages: tuple[PageInspection, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "page_count": self.page_count,
            "kind": self.kind.value,
            "median_ppi": self.median_ppi,
            "low_res_pages": list(self.low_res_pages),
            "pages": [p.to_dict() for p in self.pages],
        }


def inspect_pdf(
    path: str | Path,
    pages: Iterable[int] | None = None,
    low_res_ppi: float = LOW_RES_PPI,
) -> PdfInspection:
    """Інспектує PDF. ``pages`` — номери сторінок з 1; None — усі."""
    path = Path(path)
    with open_pdf(path) as doc:
        numbers = list(pages) if pages is not None else list(range(1, doc.page_count + 1))
        for n in numbers:
            if not 1 <= n <= doc.page_count:
                raise ValueError(f"Сторінки {n} немає (у PDF {doc.page_count} сторінок)")
        inspected = tuple(inspect_page(doc[n - 1], n) for n in numbers)
        page_count = doc.page_count

    ppis = [p.max_ppi for p in inspected if p.max_ppi]
    return PdfInspection(
        path=path.as_posix(),
        sha256=pdf_sha256(path),
        page_count=page_count,
        kind=classify_pdf(inspected),
        median_ppi=round(statistics.median(ppis), 1) if ppis else None,
        low_res_pages=tuple(p.pdf_page for p in inspected if p.max_ppi and p.max_ppi < low_res_ppi),
        pages=inspected,
    )


def save_inspection(result: PdfInspection, cache_dir: str | Path) -> Path:
    """Зберігає результат у ``<cache_dir>/<sha256>/inspect.json`` і повертає шлях."""
    return save_json(Path(cache_dir) / result.sha256 / "inspect.json", result.to_dict())


# --------------------------------------------------------------------------- CLI


def format_report(result: PdfInspection) -> str:
    """Короткий звіт для людини."""
    cats: dict[str, int] = {}
    for p in result.pages:
        cats[p.category] = cats.get(p.category, 0) + 1
    qualities = [p.text_quality for p in result.pages if p.text_chars]
    low = list(result.low_res_pages)
    lines = [
        f"Файл:          {result.path}",
        f"SHA-256:       {result.sha256[:16]}…",
        f"Сторінок:      {result.page_count} (перевірено {len(result.pages)})",
        f"Тип:           {result.kind.value}",
        f"Медіана ppi:   {result.median_ppi}",
        f"Типи сторінок: {cats}",
        f"Low-res (<{LOW_RES_PPI:g} ppi): {len(low)} стор." + (f" {low[:20]}{'…' if len(low) > 20 else ''}" if low else ""),
    ]
    if qualities:
        lines.append(f"Якість текст. шару: медіана {statistics.median(qualities):.2f}, мін {min(qualities):.2f}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Інспекція PDF перед розпізнаванням")
    parser.add_argument("pdf", help="шлях до PDF")
    parser.add_argument("--save", metavar="CACHE_DIR", help="зберегти inspect.json у цю папку кешу")
    args = parser.parse_args(argv)

    result = inspect_pdf(args.pdf)
    print(format_report(result))
    if args.save:
        print(f"Збережено: {save_inspection(result, args.save)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
