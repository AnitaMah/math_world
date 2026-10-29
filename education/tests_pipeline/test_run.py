"""Фаза 17: оркестратор на синтетичному PDF з FakeOCR (без Tesseract і мережі)."""
import json
import logging
import re
import tempfile
import unittest
from pathlib import Path

import pymupdf

from education.pdf_pipeline.config import PipelineConfig
from education.pdf_pipeline.datatypes import BBox, Word
from education.pdf_pipeline.output.export import load_textbook
from education.pdf_pipeline.run import STAGES, PipelineError, _compact_pages, _stage_range, run_pipeline

# Рядки сторінок (текст, висота шрифту в пікселях оригіналу) — як у тестах структури.
PAGES = {
    5: [("9 1. НАТУРАЛЬНІ ЧИСЛА", 20), ("1. РЯД натуральних чисел", 16.5),
        ("Числа 1, 2, 3, які використовують при лічбі, називають натуральними.", 14),
        ("Вправи", 23), ("1. Назвіть 14 перших натуральних чисел.", 14), ("2. Обчисліть:", 14),
        ("1) 2 + 3; 2) 40 - 5;", 14)],
    6: [("3. Якого числа не вистачає в записі,", 14), ("щоб він позначав натуральний ряд?", 14),
        ("4. Запишіть число.", 14)],
    7: [("сторінка, яку OCR не зміг прочитати", 14)],
}


class PagedFakeOcr:
    """Повертає слова за номером сторінки з імені файлу (``p-005.png``); стор. 7 — помилка."""

    name = "fake-paged-1"

    def __init__(self):
        self.calls = []

    def recognize(self, image, params):
        page = int(re.search(r"(\d+)", Path(image).stem).group(1))
        self.calls.append(page)
        if page == 7:
            raise RuntimeError("tesseract crashed")
        words = []
        for i, (text, h) in enumerate(PAGES.get(page, [])):
            y = 2 * (400 + i * 40)                                    # координати збільшеної вдвічі картинки
            for j, t in enumerate(text.split()):
                words.append(Word(t, BBox(2 * (150 + j * 60), y, 2 * (150 + j * 60 + 55), y + int(2 * h)), 92.0,
                                  1, 1, i + 1, j + 1))
        return words


def make_pdf(path: Path, pages: int = 7) -> None:
    doc = pymupdf.open()
    for n in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), f"page {n + 1}")
    doc.save(path)


_TOC_PATH = Path(__file__).resolve().parents[2] / "data" / "5_class_ukr.txt"


@unittest.skipUnless(_TOC_PATH.exists(), "немає змісту (авторське право — лише локально)")
class RunPipelineTests(unittest.TestCase):
    """Заголовки § і пунктів структурний парсер підтверджує звіркою зі змістом книги (structure.py),
    тому навіть на синтетичному PDF з фейковим OCR потрібна реальна (локальна, не в репозиторії) data/5_class_ukr.txt."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.pdf = root / "book.pdf"
        make_pdf(cls.pdf)
        cls.cfg = PipelineConfig(tesseract_cmd=None, tessdata_dir=None, cache_dir=root / "cache")
        cls.out = root / "out"
        cls.engine = PagedFakeOcr()
        logging.getLogger("pdf_pipeline").disabled = True       # «сторінка 7: OCR впав» — очікувано, не друкуємо
        cls.result = cls.go(report=True)

    @classmethod
    def tearDownClass(cls):
        logging.getLogger("pdf_pipeline").disabled = False
        cls.tmp.cleanup()

    @classmethod
    def go(cls, **kw):
        return run_pipeline(cls.pdf, "math_merzlyak_5", [5, 6, 7], cls.cfg, out_dir=cls.out,
                            engine_factory=lambda cfg: cls.engine, **kw)

    def test_all_stages_except_vision(self):
        self.assertEqual(self.result.stages_run, [s for s in STAGES if s != "vision"])

    def test_failed_page_is_problem_not_crash(self):
        self.assertEqual(self.result.failed_pages, {7: "ocr"})
        codes = [p.code for p in self.result.problems if p.severity == "error"]
        self.assertIn("page_failed", codes)

    def test_textbook_exported(self):
        data = load_textbook(self.result.textbook_path)
        self.assertEqual(self.result.textbook_path, self.out / "math_merzlyak_5" / "textbook.json")
        self.assertEqual(data["meta"]["pages"], [5, 6])
        self.assertGreaterEqual(data["stats"]["exercises"], 3)
        self.assertIn("page_failed", [p["code"] for p in data["problems"]])

    def test_report_and_manifest(self):
        out = self.out / "math_merzlyak_5"
        self.assertTrue((out / "report.html").exists())
        manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["params"]["pages"], "5-7")
        self.assertEqual(manifest["failed_pages"], {"7": "ocr"})
        self.assertEqual(set(manifest["timings_s"]), set(self.result.stages_run))
        self.assertEqual(len(manifest["pdf"]["sha256"]), 64)

    def test_second_run_uses_cache_and_from_stage_forces(self):
        before = len(self.engine.calls)
        again = self.go(to_stage="ocr")
        self.assertEqual(self.engine.calls[before:], [7])           # лише сторінка без кешу (бо впала)
        self.assertEqual(again.counts["ocr"]["cached"], 2)
        before = len(self.engine.calls)
        self.go(from_stage="ocr", to_stage="ocr")
        self.assertEqual(sorted(self.engine.calls[before:]), [5, 6, 7])

    def test_to_stage_stops(self):
        res = self.go(to_stage="layout")
        self.assertEqual(res.stages_run[-1], "layout")
        self.assertIsNone(res.textbook_path)
        self.assertEqual(len(res.layouts), 2)

    def test_all_pages_failed_stops_without_export(self):
        class Broken:
            name = "broken-1"

            def recognize(self, image, params):
                raise RuntimeError("Failed loading language 'ukr'")
        before = (self.out / "math_merzlyak_5" / "textbook.json").read_bytes()
        with self.assertRaisesRegex(PipelineError, "ukr"):
            run_pipeline(self.pdf, "math_merzlyak_5", [5, 6], self.cfg, out_dir=self.out,
                         engine_factory=lambda cfg: Broken())
        self.assertEqual((self.out / "math_merzlyak_5" / "textbook.json").read_bytes(), before)

    def test_vision_dry_run(self):
        res = self.go(vision_dry_run=True, report=False, to_stage="vision")
        self.assertIn("vision", res.stages_run)
        self.assertTrue(res.counts["vision"]["dry_run"])


class HelpersTests(unittest.TestCase):
    def test_compact_pages(self):
        self.assertEqual(_compact_pages([1, 2, 3, 5, 7, 8]), "1-3,5,7-8")
        self.assertEqual(_compact_pages([]), "")

    def test_stage_range(self):
        self.assertEqual(_stage_range("ocr", "export"), (3, 8))
        self.assertEqual(_stage_range(None, None), (len(STAGES), 8))
        with self.assertRaises(ValueError):
            _stage_range("export", "ocr")


if __name__ == "__main__":
    unittest.main()
