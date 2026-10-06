"""Етап 1: картинки сторінок.

Для сканованої сторінки витягаємо **оригінальну** картинку з PDF (без
перерендеру — так не губимо якість і не роздуваємо розмір). Якщо сторінка
не є одним сканом (текстовий PDF, кілька картинок) — рендеримо її.

Результат кешується: ``<cache_dir>/<sha256>/pages/p-005.png`` + ``p-005.json``
(метадані PageImage). Повторний виклик лише читає JSON.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import pymupdf

from .cache import load_json, save_json
from .config import PipelineConfig
from .datatypes import PageImage
from .pdf_inspect import FULL_PAGE_COVERAGE, LOW_RES_PPI, open_pdf, pdf_sha256

DEFAULT_RENDER_DPI = 200   # для сторінок без скану (текстовий PDF)

_RANGE_PART_RE = re.compile(r"^(\d+)(?:\s*-\s*(\d+))?$")


# --------------------------------------------------------------------------- діапазони сторінок


def parse_page_range(spec: str) -> list[int]:
    """Перетворює "5-7, 10,12-13" на [5, 6, 7, 10, 12, 13] (без дублікатів, по зростанню).

    Номери сторінок з 1. Помилка на 0, на "7-5" і на сміття.
    """
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        match = _RANGE_PART_RE.match(part)
        if not match:
            raise ValueError(f"Незрозумілий діапазон сторінок: {part!r}")
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        if start < 1:
            raise ValueError(f"Сторінки нумеруються з 1, а не {start}")
        if end < start:
            raise ValueError(f"Діапазон навпаки: {part!r}")
        pages.update(range(start, end + 1))
    if not pages:
        raise ValueError("Порожній діапазон сторінок")
    return sorted(pages)


# --------------------------------------------------------------------------- витяг і рендер


def _to_rgb(pix: pymupdf.Pixmap) -> pymupdf.Pixmap:
    """CMYK / з прозорістю / grayscale-з-альфою → RGB або Gray без альфи (PNG-сумісно)."""
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)                     # прибрати альфа-канал
    if pix.colorspace and pix.colorspace.n not in (1, 3):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)         # напр. CMYK (n=4) → RGB
    return pix


def find_full_page_image(page: pymupdf.Page) -> tuple[int, float] | None:
    """Якщо сторінка — це один скан на всю площу, повертає (xref, ppi), інакше None."""
    images = page.get_images(full=True)
    if len(images) != 1:
        return None
    xref, px_width = images[0][0], images[0][2]
    rects = page.get_image_rects(xref)
    if len(rects) != 1:
        return None
    shown = rects[0]
    page_area = page.rect.width * page.rect.height
    if page_area <= 0 or shown.width <= 0:
        return None
    if (shown.width * shown.height) / page_area < FULL_PAGE_COVERAGE:
        return None
    return xref, px_width / (shown.width / 72.0)


def extract_native_image(doc: pymupdf.Document, page: pymupdf.Page, out_path: Path) -> float | None:
    """Зберігає оригінальну картинку скану як PNG. Повертає її ppi або None, якщо це не скан."""
    found = find_full_page_image(page)
    if found is None:
        return None
    xref, ppi = found
    pix = _to_rgb(pymupdf.Pixmap(doc, xref))
    if page.rotation:
        # Сторінка повернута в PDF — повертаємо картинку так, як її бачить читач.
        from PIL import Image
        img = Image.frombytes("RGB" if pix.n == 3 else "L", (pix.width, pix.height), pix.samples)
        img.rotate(-page.rotation, expand=True).save(out_path)
    else:
        pix.save(out_path)
    return ppi


def render_page(page: pymupdf.Page, out_path: Path, dpi: int) -> None:
    """Рендерить сторінку в PNG із заданим dpi (з урахуванням повороту)."""
    page.get_pixmap(dpi=dpi, alpha=False).save(out_path)


# --------------------------------------------------------------------------- кеш і API


def page_image_path(cache_dir: Path, sha: str, pdf_page: int, dpi: int | None = None) -> Path:
    """``<cache_dir>/<sha>/pages/p-007.png``; з примусовим dpi — ``p-007@300dpi.png``.

    Окреме ім'я для примусового dpi, щоб експеримент не перезаписав оригінальний скан.
    """
    suffix = f"@{dpi}dpi" if dpi else ""
    return Path(cache_dir) / sha / "pages" / f"p-{pdf_page:03d}{suffix}.png"


def _meta_path(png_path: Path) -> Path:
    return png_path.with_suffix(".json")


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image
    with Image.open(path) as img:
        return img.size


def _get_page_image(
    doc: pymupdf.Document,
    sha: str,
    pdf_page: int,
    cfg: PipelineConfig,
    force: bool = False,
    force_dpi: int | None = None,
) -> PageImage:
    """Внутрішня версія з уже відкритим документом і порахованим sha (щоб не робити це 300 разів)."""
    if not 1 <= pdf_page <= doc.page_count:
        raise ValueError(f"Сторінки {pdf_page} немає (у PDF {doc.page_count} сторінок)")

    out = page_image_path(cfg.cache_dir, sha, pdf_page, force_dpi)
    meta = _meta_path(out)
    if not force and out.exists() and meta.exists():
        return PageImage.from_dict(load_json(meta))

    out.parent.mkdir(parents=True, exist_ok=True)
    page = doc[pdf_page - 1]

    ppi = None if force_dpi else extract_native_image(doc, page, out)
    if ppi is None:
        dpi = force_dpi or DEFAULT_RENDER_DPI
        render_page(page, out, dpi)
        ppi = float(dpi)

    width, height = _image_size(out)
    result = PageImage(
        pdf_page=pdf_page,
        path=out,
        width=width,
        height=height,
        dpi=round(ppi, 1),
        low_res=ppi < LOW_RES_PPI,
    )
    save_json(meta, result.to_dict())
    return result


def get_page_image(
    pdf_path: str | Path,
    pdf_page: int,
    cfg: PipelineConfig,
    force: bool = False,
    force_dpi: int | None = None,
) -> PageImage:
    """Картинка однієї сторінки (з кешу або щойно витягнута).

    :param force: ігнорувати кеш і створити заново.
    :param force_dpi: рендерити з цим dpi замість витягу оригіналу (для експериментів);
        зберігається в окремий файл ``p-007@300dpi.png``.
    """
    sha = pdf_sha256(pdf_path)
    with open_pdf(pdf_path) as doc:
        return _get_page_image(doc, sha, pdf_page, cfg, force, force_dpi)


def get_page_images(
    pdf_path: str | Path,
    pages: Iterable[int],
    cfg: PipelineConfig,
    force: bool = False,
) -> list[PageImage]:
    """Картинки кількох сторінок; PDF відкривається і хешується один раз."""
    sha = pdf_sha256(pdf_path)
    with open_pdf(pdf_path) as doc:
        return [_get_page_image(doc, sha, n, cfg, force) for n in pages]
