"""Рушій текстового шару PDF: слова з координатами в пікселях оригінальної картинки."""
import tempfile
import unittest
from pathlib import Path

import pymupdf

from education.pdf_pipeline.datatypes import PageImage
from education.pdf_pipeline.ocr.pdftext import PdfTextEngine


class PdfTextEngineTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.pdf = Path(self.dir) / "t.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=200, height=100)
        page.insert_text((20, 30), "12. Обчисліть: 98 . 34;", fontname="helv", fontsize=10)
        doc.save(self.pdf)

    def test_words_scaled_to_image_pixels(self):
        engine = PdfTextEngine(self.pdf)
        page = PageImage(pdf_page=1, path=Path("p-001.png"), width=400, height=200, dpi=144)   # ×2
        words = engine.recognize_page(page)
        self.assertEqual(words[0].text, "12.")
        self.assertTrue(all(w.conf > 90 for w in words))
        x0 = min(w.bbox.x0 for w in words)
        self.assertTrue(38 <= x0 <= 42, x0)              # 20 pt × 2 = 40 px
        self.assertLess(words[0].bbox.x0, words[-1].bbox.x0)

    def test_name_identifies_engine(self):
        self.assertTrue(PdfTextEngine(self.pdf).name.startswith("pdftext-"))
