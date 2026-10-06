"""Спільний інтерфейс OCR-рушіїв. Сьогодні — Tesseract, завтра — будь-який інший."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Union

import numpy as np

from ..cache import short_hash
from ..datatypes import Line, Word

ImageInput = Union[str, Path, np.ndarray]


@dataclass(frozen=True)
class OcrParams:
    """Параметри розпізнавання.

    lang — мови Tesseract (`ukr+eng`: eng потрібна для латинських змінних a, x).
    psm  — режим розбивки сторінки: 3 авто, 4 одна колонка, 6 один блок, 11 розкиданий текст.
    oem  — рушій: 1 = нейромережа LSTM (найкращий).
    """

    lang: str = "ukr+eng"
    psm: int = 4              # переможець бенчмарку (BENCH.md, 2026-10-06)
    oem: int = 1
    extra: tuple[tuple[str, str], ...] = ()   # додаткові `-c ключ=значення`

    def cache_key(self) -> str:
        return short_hash(self.lang, self.psm, self.oem, list(self.extra))

    def to_dict(self) -> dict:
        return {"lang": self.lang, "psm": self.psm, "oem": self.oem, "extra": [list(e) for e in self.extra]}


class OcrEngine(Protocol):
    """Будь-який клас з такими атрибутами і методом підходить як OCR-рушій."""

    @property
    def name(self) -> str: ...            # напр. "tesseract-5.5.3" — входить у ключ кешу

    def recognize(self, image: ImageInput, params: OcrParams) -> list[Word]: ...


class FakeOcrEngine:
    """Рушій для тестів: повертає наперед задані слова, рахує виклики."""

    name = "fake-1"

    def __init__(self, words: Sequence[Word]):
        self.words = list(words)
        self.calls = 0

    def recognize(self, image: ImageInput, params: OcrParams) -> list[Word]:
        self.calls += 1
        return list(self.words)


def words_to_lines(words: Sequence[Word], page_index: int) -> list[Line]:
    """Групує слова в рядки за номерами (block, par, line) від Tesseract.

    Рядки сортуються згори вниз (за верхнім краєм), слова в рядку — зліва направо.
    """
    groups: dict[tuple[int, int, int], list[Word]] = {}
    for w in words:
        groups.setdefault((w.block_no, w.par_no, w.line_no), []).append(w)

    lines = [Line(words=sorted(ws, key=lambda w: w.bbox.x0), page_index=page_index)
             for ws in groups.values()]
    lines.sort(key=lambda ln: (ln.bbox.y0, ln.bbox.x0))
    for i, line in enumerate(lines):
        line.line_id = i
    return lines
