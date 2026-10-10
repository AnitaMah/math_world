"""0871: відновлення після переривання (Ctrl+C, обрив світла) — кеш дозволяє продовжити з місця зупинки."""
import logging
import shutil
import tempfile
import unittest
from pathlib import Path

from education.pdf_pipeline.config import PipelineConfig
from education.pdf_pipeline.run import run_pipeline
from education.tests_pipeline.test_run import PagedFakeOcr, make_pdf

PAGES = [3, 5, 6]            # 3 — порожня, 5 і 6 — зі змістом (див. PAGES у test_run)


class InterruptingOcr(PagedFakeOcr):
    """Як PagedFakeOcr, але на сторінці `stop_on` кидає KeyboardInterrupt (користувач натиснув Ctrl+C)."""

    name = "fake-interrupt-1"

    def __init__(self, stop_on=None):
        super().__init__()
        self.stop_on = stop_on

    def recognize(self, image, params):
        import re
        page = int(re.search(r"(\d+)", Path(image).stem).group(1))
        if page == self.stop_on:
            raise KeyboardInterrupt
        return super().recognize(image, params)


class ResumeAfterInterruptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Сторінки рендеримо й обробляємо один раз (це найповільніше); ocr/ кожен тест починає з нуля."""
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.pdf = root / "book.pdf"
        make_pdf(cls.pdf)
        cls.base_cache = root / "base_cache"
        cfg = PipelineConfig(tesseract_cmd=None, tessdata_dir=None, cache_dir=cls.base_cache)
        logging.getLogger("pdf_pipeline").disabled = True
        run_pipeline(cls.pdf, "math_merzlyak_5", PAGES, cfg, out_dir=root / "out0", to_stage="preprocess")

    @classmethod
    def tearDownClass(cls):
        logging.getLogger("pdf_pipeline").disabled = False
        cls.tmp.cleanup()

    def setUp(self):
        """Метадані кешу містять абсолютні шляхи, тож копія кешу не годиться: чистимо лише ocr/ спільного кешу."""
        for d in self.base_cache.glob("*/ocr"):
            shutil.rmtree(d)
        self.cfg = PipelineConfig(tesseract_cmd=None, tessdata_dir=None, cache_dir=self.base_cache)
        self.out = Path(self.tmp.name) / "out"

    def go(self, engine, **kw):
        return run_pipeline(self.pdf, "math_merzlyak_5", PAGES, self.cfg, out_dir=self.out,
                            engine_factory=lambda cfg: engine, **kw)

    def ocr_dir(self):
        return next((self.cfg.cache_dir).glob("*/ocr"))

    def test_ctrl_c_in_ocr_then_resume_skips_finished_pages(self):
        first = InterruptingOcr(stop_on=6)
        with self.assertRaises(KeyboardInterrupt):
            self.go(first)
        self.assertEqual(first.calls, [3, 5])                    # 3 і 5 встигли, на 6 — Ctrl+C

        second = InterruptingOcr()
        res = self.go(second)
        self.assertEqual(second.calls, [6])                      # розпізнано лише те, що не встигли
        self.assertEqual(res.counts["ocr"]["cached"], 2)
        self.assertEqual(res.counts["ocr"]["recognized"], 1)
        self.assertEqual(res.failed_pages, {})
        self.assertIsNotNone(res.textbook_path)

    def test_resumed_result_equals_uninterrupted_run(self):
        with self.assertRaises(KeyboardInterrupt):
            self.go(InterruptingOcr(stop_on=5))
        resumed = self.go(InterruptingOcr())
        clean = self.go(InterruptingOcr(), force=True)
        self.assertEqual([lay.pdf_page for lay in resumed.layouts], [lay.pdf_page for lay in clean.layouts])
        self.assertEqual(resumed.counts["layout"], clean.counts["layout"])
        self.assertEqual(resumed.textbook_path.read_text(encoding="utf-8").count('"number"'),
                         clean.textbook_path.read_text(encoding="utf-8").count('"number"'))

    def test_leftover_tmp_file_is_harmless(self):
        self.go(InterruptingOcr(), to_stage="ocr")
        d = self.ocr_dir()
        (next(d.rglob("*.json")).parent / "p-005.json.abc123.tmp").write_text("{обірвано")
        engine = InterruptingOcr()
        res = self.go(engine, to_stage="ocr")
        self.assertEqual(engine.calls, [])
        self.assertEqual(res.counts["ocr"]["cached"], 3)

    def test_truncated_cache_file_is_recomputed(self):
        self.go(InterruptingOcr(), to_stage="ocr")
        victim = sorted(self.ocr_dir().rglob("*.json"))[1]       # сторінка 5: обрізаний файл (аварійне вимкнення)
        victim.write_text(victim.read_text(encoding="utf-8")[:40], encoding="utf-8")
        engine = InterruptingOcr()
        res = self.go(engine, to_stage="ocr")
        self.assertEqual(len(engine.calls), 1)                   # перерахована рівно одна сторінка
        self.assertEqual(res.failed_pages, {})

    def test_truncated_image_meta_is_rebuilt(self):
        self.go(InterruptingOcr(), to_stage="images")
        meta = next(self.cfg.cache_dir.glob("*/pages/*.json"))
        meta.write_text("{", encoding="utf-8")
        res = self.go(InterruptingOcr(), to_stage="images")
        self.assertEqual(res.failed_pages, {})


class PageImageCacheTests(unittest.TestCase):
    """0870: у пам'яті тримається не більше кількох сторінок, а не вся книга."""

    def setUp(self):
        import cv2
        import numpy as np
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = {}
        for n in range(1, 8):
            p = Path(self.tmp.name) / f"p{n}.png"
            cv2.imwrite(str(p), np.full((20, 20, 3), n, dtype=np.uint8))
            self.paths[n] = p

    def tearDown(self):
        self.tmp.cleanup()

    def test_keeps_at_most_size_pages_and_reuses_recent(self):
        from education.pdf_pipeline.preprocess import PageImageCache
        cache = PageImageCache(self.paths, size=3)
        for n in range(1, 8):
            self.assertEqual(int(cache.get(n)[0, 0, 0]), n)
        self.assertEqual(len(cache._items), 3)
        self.assertEqual(cache.loads, 7)
        cache.get(7), cache.get(6)                     # свіжі сторінки — з пам'яті
        self.assertEqual(cache.loads, 7)
        cache.get(1)                                   # давно витіснена — читаємо знову
        self.assertEqual(cache.loads, 8)

    def test_unknown_page_is_none(self):
        from education.pdf_pipeline.preprocess import PageImageCache
        cache = PageImageCache(self.paths)
        self.assertIsNone(cache.get(99))
        self.assertIsNone(cache.get(None))
        self.assertIn(3, cache)
