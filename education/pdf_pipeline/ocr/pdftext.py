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

    VERSION = "1"

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
        for x0, y0, x1, y1, text, block, line, idx in pdf_page.get_text("words", sort=True):
            parts = text.replace("\xa0", " ").split()
            if not parts:
                continue
            total = sum(len(p) for p in parts) or 1
            cursor = x0
            for k, part in enumerate(parts):      # «6 учнів» з нерозривним пробілом → два слова
                x_end = x1 if k == len(parts) - 1 else cursor + (x1 - x0) * len(part) / total
                words.append(Word(
                    text=part,
                    bbox=BBox(int(cursor * sx), int(y0 * sy), max(int(cursor * sx), round(x_end * sx)),
                              max(int(y0 * sy), round(y1 * sy))),
                    conf=LAYER_CONF, block_no=block, par_no=0, line_no=line, word_no=idx + k))
                cursor = x_end
        return words
