"""Етап 3: OCR сторінки з кешем.

``ocr_page(prepared, engine, params)`` розпізнає підготовлену картинку і
повертає ``PageOcr``, де координати слів уже переведені в систему
**оригінальної** картинки сторінки (через Transform з препроцесингу).
"""
from __future__ import annotations

import dataclasses
import time
from pathlib import Path

from ..cache import load_json, save_json, short_hash
from ..datatypes import PageOcr
from ..preprocess import PreparedPage
from .base import FakeOcrEngine, OcrEngine, OcrParams, words_to_lines

__all__ = ["FakeOcrEngine", "OcrEngine", "OcrParams", "ocr_cache_path", "ocr_page", "words_to_lines"]


def ocr_cache_path(prepared: PreparedPage, engine: OcrEngine, params: OcrParams) -> Path:
    """``<cache>/<sha>/ocr/<key>/p-007.json``; key залежить від рецепту, параметрів і рушія."""
    key = short_hash(prepared.spec_key, params.cache_key(), engine.name)
    sha_dir = prepared.page.path.parent.parent
    return sha_dir / "ocr" / key / prepared.page.path.with_suffix(".json").name


def ocr_page(prepared: PreparedPage, engine: OcrEngine, params: OcrParams | None = None,
             force: bool = False) -> PageOcr:
    """Розпізнає сторінку (або бере з кешу)."""
    params = params or OcrParams()
    out = ocr_cache_path(prepared, engine, params)
    if not force and out.exists():
        return PageOcr.from_dict(load_json(out))

    started = time.perf_counter()
    raw_words = engine.recognize(prepared.path, params)
    duration_ms = int((time.perf_counter() - started) * 1000)

    words = [dataclasses.replace(w, bbox=prepared.transform.to_original(w.bbox)) for w in raw_words]
    result = PageOcr(
        page=prepared.page,
        words=words,
        engine=engine.name,
        params={**params.to_dict(), "preprocess": prepared.spec_name},
        duration_ms=duration_ms,
    )
    save_json(out, result.to_dict())
    return result
