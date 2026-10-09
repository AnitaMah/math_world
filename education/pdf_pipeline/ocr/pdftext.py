"""«OCR» зі вбудованого текстового шару PDF (PyMuPDF): слова з координатами без розпізнавання.

Є, коли PDF — скан із якісним шаром тексту (повний Мерзляк-5 2018): шар точніший за Tesseract
(зберігає «·» множення, «•»/«••» складності, дужки), працює за секунди й не потребує мовних моделей.
Для скану без шару (Тарасенкова, стор. 1–46 Мерзляка) лишається Tesseract.

Координати слів — у пікселях *оригінальної* картинки сторінки (пункти PDF × ширина картинки / ширина сторінки),
тому рушій має метод ``recognize_page`` і ``ocr_page`` не застосовує Transform препроцесингу.
"""
from __future__ import annotations

from pathlib import Path

import pymupdf

from ..datatypes import BBox, PageImage, Word
from .base import OcrParams

LAYER_CONF = 99.0       # текстовий шар — не «впевненість OCR», але й не 100: щоб low_conf не вмикав вручну


class PdfTextEngine:
    """Рушій, що читає текстовий шар. Один екземпляр тримає відкритий PDF (створюється в кожному процесі)."""

    VERSION = "3"

    def __init__(self, pdf_path: str | Path):
        self.pdf_path = Path(pdf_path)
        self._doc: pymupdf.Document | None = None

    @property
    def name(self) -> str:
        return f"pdftext-{self.VERSION}-{pymupdf.version[0]}"

    def _open(self) -> pymupdf.Document:
        if self._doc is None:
            self._doc = pymupdf.open(self.pdf_path)
        return self._doc

    def recognize(self, image, params: OcrParams) -> list[Word]:       # pragma: no cover — інтерфейс Protocol
        raise NotImplementedError("PdfTextEngine працює зі сторінкою PDF: recognize_page()")

    def recognize_page(self, page: PageImage) -> list[Word]:
        pdf_page = self._open()[page.pdf_page - 1]
        rect = pdf_page.rect
        sx, sy = page.width / rect.width, page.height / rect.height
        words: list[Word] = []
        raw = pdf_page.get_text("rawdict")
        for block_no, block in enumerate(raw["blocks"]):
            if block.get("type") != 0:
                continue
            for line_no, line in enumerate(block["lines"]):
                for chars in _split_words(line):
                    text = "".join(c for c, _ in chars)
                    x0 = min(b[0] for _, b in chars)
                    y0 = min(b[1] for _, b in chars)
                    x1 = max(b[2] for _, b in chars)
                    y1 = max(b[3] for _, b in chars)
                    words.append(Word(
                        text=text,
                        bbox=BBox(int(x0 * sx), int(y0 * sy), max(int(x0 * sx), round(x1 * sx)),
                                  max(int(y0 * sy), round(y1 * sy))),
                        conf=LAYER_CONF, block_no=block_no, par_no=0, line_no=line_no, word_no=len(words)))
        return words


_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _split_words(line: dict) -> list[list[tuple[str, tuple]]]:
    """Рядок rawdict → слова (списки (символ, bbox)); цифри верхнього індексу стають «²», «³» …

    Верхній індекс — фрагмент дрібніший за 75% найбільшого кеглю рядка (показник 6 pt проти 10 pt)
    і піднятий над базовою лінією. Прапорець superscript не беремо: його мають і чисельники дробів (9 pt).
    «26²» інакше читалось би як «262» і ламало обчислення.
    """
    spans = line["spans"]
    biggest = max((sp["size"] for sp in spans), default=0)
    baseline = max((sp["origin"][1] for sp in spans), default=0)
    words: list[list[tuple[str, tuple]]] = []
    current: list[tuple[str, tuple]] = []
    for sp in spans:
        sup = sp["size"] < biggest * 0.75 and sp["origin"][1] < baseline - sp["size"] * 0.25
        for ch in sp["chars"]:
            c = ch["c"]
            if c.isspace():
                if current:
                    words.append(current)
                    current = []
                continue
            if sup and c.isdigit():
                c = c.translate(_SUPERSCRIPT)
            current.append((c, ch["bbox"]))
    if current:
        words.append(current)
    return words
