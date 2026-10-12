"""Тести для OCR-етапу, кешу і бенчмарку."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from education.pdf_pipeline import cache
from education.pdf_pipeline.bench import cer, normalize_for_cer
from education.pdf_pipeline.config import PipelineConfig
from education.pdf_pipeline.datatypes import BBox, PageImage, Word
from education.pdf_pipeline.ocr import FakeOcrEngine, OcrParams, ocr_cache_path, ocr_page, words_to_lines
from education.pdf_pipeline.ocr.tesseract import TesseractEngine, TesseractNotAvailable, parse_tesseract_data
from education.pdf_pipeline.preprocess import PreparedPage, Transform, _scale_matrix

ROOT = Path(__file__).resolve().parents[2]
MERZLYAK_PDF = ROOT / "5-klas-matematika-merzljak-2018-1-46.pdf"


def w(text, x0, y0, x1, y1, block=1, par=1, line=1, conf=90.0):
    return Word(text, BBox(x0, y0, x1, y1), conf, block, par, line)


class CacheTests(unittest.TestCase):
    def test_save_and_load_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = cache.save_json(Path(tmp) / "a" / "b.json", {"текст": [1, 2]})
            self.assertEqual(cache.load_json(path), {"текст": [1, 2]})
            self.assertEqual([p.name for p in path.parent.iterdir()], ["b.json"])   # без .tmp-сміття

    def test_failed_write_keeps_old_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = cache.save_json(Path(tmp) / "x.json", {"ok": 1})
            with self.assertRaises(TypeError):
                cache.save_json(path, {"bad": object()})          # не серіалізується
            self.assertEqual(cache.load_json(path), {"ok": 1})
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)

    def test_short_hash(self):
        self.assertEqual(cache.short_hash("a", 1), cache.short_hash("a", 1))
        self.assertNotEqual(cache.short_hash("a", 1), cache.short_hash("a", 2))
        self.assertEqual(len(cache.short_hash("a")), 12)


class OcrParamsTests(unittest.TestCase):
    def test_cache_key(self):
        self.assertEqual(OcrParams().cache_key(), OcrParams().cache_key())
        self.assertNotEqual(OcrParams(psm=6).cache_key(), OcrParams(psm=4).cache_key())


class ParseTesseractDataTests(unittest.TestCase):
    def test_keeps_only_real_words(self):
        data = {
            "level":     [1, 4, 5, 5, 5],
            "text":      ["", "", "Вправи", "  ", "для"],
            "conf":      ["-1", "-1", "96.5", "95", "-1"],
            "left":      [0, 10, 10, 50, 80],
            "top":       [0, 20, 20, 20, 20],
            "width":     [100, 90, 35, 5, 30],
            "height":    [100, 15, 15, 15, 15],
            "block_num": [0, 1, 1, 1, 1], "par_num": [0, 1, 1, 1, 1],
            "line_num":  [0, 1, 1, 1, 1], "word_num": [0, 0, 1, 2, 3],
        }
        words = parse_tesseract_data(data)
        self.assertEqual([x.text for x in words], ["Вправи"])
        self.assertEqual(words[0].bbox, BBox(10, 20, 45, 35))
        self.assertEqual(words[0].conf, 96.5)


class WordsToLinesTests(unittest.TestCase):
    def test_groups_and_orders(self):
        words = [
            w("числами:", 300, 100, 380, 120, line=2),
            w("12.", 0, 10, 30, 30, line=1),
            w("Скільки", 40, 100, 120, 120, line=2),
            w("Обчисліть:", 40, 12, 150, 30, line=1),
        ]
        lines = words_to_lines(words, page_index=7)
        self.assertEqual([ln.text for ln in lines], ["12. Обчисліть:", "Скільки числами:"])
        self.assertEqual([ln.line_id for ln in lines], [0, 1])
        self.assertEqual(lines[0].page_index, 7)


class OcrPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        sha_dir = Path(self.tmp.name) / "sha"
        page = PageImage(7, sha_dir / "pages" / "p-007.png", 100, 200, 150.0)
        self.prepared = PreparedPage(
            page=page, path=sha_dir / "prep" / "k" / "p-007.png", spec_name="default",
            spec_key="k", transform=Transform().then(_scale_matrix(2)),   # оброблена картинка ×2
        )
        self.engine = FakeOcrEngine([w("Вправи", 20, 40, 120, 60)])

    def tearDown(self):
        self.tmp.cleanup()

    def test_bbox_returned_to_original_coordinates(self):
        result = ocr_page(self.prepared, self.engine)
        self.assertEqual(result.words[0].bbox, BBox(10, 20, 60, 30))   # поділено на 2
        self.assertEqual(result.page.pdf_page, 7)
        self.assertEqual(result.engine, "fake-1")
        self.assertEqual(result.params["preprocess"], "default")

    def test_cache(self):
        first = ocr_page(self.prepared, self.engine)
        second = ocr_page(self.prepared, self.engine)
        self.assertEqual(self.engine.calls, 1)
        self.assertEqual(first, second)
        ocr_page(self.prepared, self.engine, force=True)
        self.assertEqual(self.engine.calls, 2)

    def test_cache_key_depends_on_params(self):
        a = ocr_cache_path(self.prepared, self.engine, OcrParams(psm=6))
        b = ocr_cache_path(self.prepared, self.engine, OcrParams(psm=4))
        self.assertNotEqual(a, b)
        self.assertEqual(a.name, "p-007.json")


class TesseractConfigTests(unittest.TestCase):
    def test_build_config(self):
        engine = TesseractEngine.__new__(TesseractEngine)   # без запуску tesseract
        engine.cfg = PipelineConfig(None, Path("C:/tessdata_best"), Path("c"))
        config = engine.build_config(OcrParams(psm=4, extra=(("tessedit_do_invert", "0"),)))
        self.assertIn("--psm 4", config)
        self.assertIn("--oem 1", config)
        self.assertNotIn("tessdata", config)          # шлях іде через TESSDATA_PREFIX (лапки ламали Windows)
        self.assertIn("-c tessedit_do_invert=0", config)


class CerTests(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(cer("Вправи для повторення", "Вправи для повторення"), 0.0)

    def test_normalization_ignores_layout(self):
        ocr = "натураль-\nних  чисел — «так»"
        golden = "натуральних чисел - \"так\""
        self.assertEqual(normalize_for_cer(ocr), normalize_for_cer(golden))
        self.assertEqual(cer(ocr, golden), 0.0)

    def test_one_error_in_ten(self):
        self.assertAlmostEqual(cer("абвгдеєжзи"[:-1] + "x", "абвгдеєжзи"), 0.1)

    def test_empty_reference(self):
        self.assertEqual(cer("", ""), 0.0)
        self.assertEqual(cer("щось", ""), 1.0)


def _tesseract_with_ukr():
    try:
        engine = TesseractEngine(PipelineConfig.from_env())
    except TesseractNotAvailable:
        return None
    import pytesseract
    return engine if "ukr" in pytesseract.get_languages() else None


@unittest.skipUnless(MERZLYAK_PDF.exists() and _tesseract_with_ukr(), "немає Tesseract з ukr або PDF")
class RealTesseractTests(unittest.TestCase):
    """Повільний тест (~10–60 с перший раз, далі з кешу)."""

    def test_page_7(self):
        from education.pdf_pipeline.images import get_page_image
        from education.pdf_pipeline.preprocess import preprocess_page
        cfg = PipelineConfig.from_env()
        engine = TesseractEngine(cfg)
        result = ocr_page(preprocess_page(get_page_image(MERZLYAK_PDF, 7, cfg)), engine)
        lines = [ln.text for ln in words_to_lines(result.words, 7)]
        self.assertGreater(len(result.words), 100)
        self.assertTrue(any("Вправи для повторення" in t for t in lines))
        self.assertTrue(all(wd.bbox.x1 <= result.page.width + 2 for wd in result.words))   # координати оригіналу


if __name__ == "__main__":
    unittest.main()


class TesseractTimeoutRetryTests(unittest.TestCase):
    def engine(self, timeout=10):
        engine = TesseractEngine.__new__(TesseractEngine)
        engine.cfg = PipelineConfig(None, None, Path("c"))
        engine.timeout = timeout
        return engine

    def test_timeout_is_retried_with_longer_limit(self):
        from unittest import mock
        calls = []

        def fake(image, lang, config, output_type, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise RuntimeError("Tesseract process timeout")
            return {"level": [], "text": []}

        with mock.patch("pytesseract.image_to_data", fake):
            self.assertEqual(self.engine().recognize("x.png", OcrParams()), [])
        self.assertEqual(calls, [10, 30])

    def test_other_errors_are_not_retried(self):
        from unittest import mock
        with mock.patch("pytesseract.image_to_data", side_effect=RuntimeError("boom")) as m:
            with self.assertRaises(RuntimeError):
                self.engine().recognize("x.png", OcrParams())
        self.assertEqual(m.call_count, 1)

    def test_timeout_from_env(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"TESSERACT_TIMEOUT": "300"}), \
                mock.patch("pytesseract.get_tesseract_version", return_value="5"):
            self.assertEqual(TesseractEngine(PipelineConfig(None, None, Path("c"))).timeout, 300.0)
