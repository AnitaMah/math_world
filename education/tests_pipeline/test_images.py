"""Тести для education.pdf_pipeline.images."""
import tempfile
import unittest
from pathlib import Path

import pymupdf
from PIL import Image

from education.pdf_pipeline.config import PipelineConfig
from education.pdf_pipeline.images import (
    DEFAULT_RENDER_DPI, get_page_image, get_page_images, page_image_path, parse_page_range,
)
from education.pdf_pipeline.pdf_inspect import pdf_sha256

ROOT = Path(__file__).resolve().parents[2]
MERZLYAK_PDF = ROOT / "5-klas-matematika-merzljak-2018-1-46.pdf"


def make_scan_pdf(path: Path, px=(200, 300), pt=(144, 216), colorspace=None, rotate=0, pages=1) -> None:
    """PDF-«скан»: на кожній сторінці одна картинка на всю площу, з чорним квадратом зліва вгорі."""
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page(width=pt[0], height=pt[1])
        pix = pymupdf.Pixmap(colorspace or pymupdf.csRGB, pymupdf.IRect(0, 0, *px), False)
        pix.clear_with(255)
        pix.set_rect(pymupdf.IRect(0, 0, 20, 20), (0,) * pix.n)   # мітка, щоб бачити орієнтацію
        page.insert_image(page.rect, pixmap=pix)
        if rotate:
            page.set_rotation(rotate)
    doc.save(path)


class ParsePageRangeTests(unittest.TestCase):
    def test_single_and_ranges(self):
        self.assertEqual(parse_page_range("5-7,10, 12 - 13"), [5, 6, 7, 10, 12, 13])

    def test_duplicates_and_order(self):
        self.assertEqual(parse_page_range("10,3,3,2-4"), [2, 3, 4, 10])

    def test_errors(self):
        for bad in ["7-5", "0", "abc", "1-", "", " , "]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_page_range(bad)


class PageImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cfg = PipelineConfig(tesseract_cmd=None, tessdata_dir=None, cache_dir=self.dir / "cache")

    def tearDown(self):
        self.tmp.cleanup()

    def test_native_extraction_keeps_original_size(self):
        pdf = self.dir / "scan.pdf"
        make_scan_pdf(pdf, px=(200, 300), pt=(144, 216))   # 100 ppi
        img = get_page_image(pdf, 1, self.cfg)
        self.assertEqual((img.width, img.height), (200, 300))
        self.assertAlmostEqual(img.dpi, 100, delta=1)
        self.assertTrue(img.low_res)
        self.assertTrue(img.path.exists())
        self.assertEqual(img.path, page_image_path(self.cfg.cache_dir, pdf_sha256(pdf), 1))

    def test_cmyk_becomes_rgb_png(self):
        pdf = self.dir / "cmyk.pdf"
        make_scan_pdf(pdf, colorspace=pymupdf.csCMYK)
        img = get_page_image(pdf, 1, self.cfg)
        with Image.open(img.path) as im:
            self.assertEqual(im.mode, "RGB")

    def test_rotated_page(self):
        pdf = self.dir / "rot.pdf"
        make_scan_pdf(pdf, px=(200, 300), pt=(144, 216), rotate=90)
        img = get_page_image(pdf, 1, self.cfg)
        self.assertEqual((img.width, img.height), (300, 200))   # ширина і висота помінялися
        # Чорна мітка була зліва вгорі; після повороту на 90° за годинниковою — справа вгорі,
        # так само, як показує звичайний рендер сторінки.
        with Image.open(img.path) as im:
            gray = im.convert("L")
            self.assertLess(gray.getpixel((294, 5)), 100)
            self.assertGreater(gray.getpixel((5, 5)), 200)

    def test_born_digital_page_is_rendered(self):
        pdf = self.dir / "text.pdf"
        doc = pymupdf.open()
        doc.new_page(width=144, height=216).insert_text((20, 40), "Hello")
        doc.save(pdf)
        img = get_page_image(pdf, 1, self.cfg)
        self.assertEqual(img.dpi, DEFAULT_RENDER_DPI)
        self.assertEqual(img.width, round(144 / 72 * DEFAULT_RENDER_DPI))

    def test_cache_is_reused(self):
        pdf = self.dir / "scan.pdf"
        make_scan_pdf(pdf)
        first = get_page_image(pdf, 1, self.cfg)
        mtime = first.path.stat().st_mtime_ns
        second = get_page_image(pdf, 1, self.cfg)
        self.assertEqual(first, second)
        self.assertEqual(second.path.stat().st_mtime_ns, mtime)   # файл не перезаписувався

    def test_force_dpi_goes_to_separate_file(self):
        pdf = self.dir / "scan.pdf"
        make_scan_pdf(pdf, pt=(144, 216))
        native = get_page_image(pdf, 1, self.cfg)
        forced = get_page_image(pdf, 1, self.cfg, force_dpi=300)
        self.assertNotEqual(native.path, forced.path)
        self.assertEqual((forced.width, forced.height), (600, 900))
        self.assertEqual(get_page_image(pdf, 1, self.cfg), native)   # оригінал не зіпсовано

    def test_bad_page(self):
        pdf = self.dir / "scan.pdf"
        make_scan_pdf(pdf)
        with self.assertRaises(ValueError):
            get_page_image(pdf, 2, self.cfg)

    def test_many_pages(self):
        pdf = self.dir / "three.pdf"
        make_scan_pdf(pdf, pages=3)
        imgs = get_page_images(pdf, [1, 3], self.cfg)
        self.assertEqual([i.pdf_page for i in imgs], [1, 3])
        self.assertEqual(imgs[1].path.name, "p-003.png")


@unittest.skipUnless(MERZLYAK_PDF.exists(), "немає PDF Мерзляка")
class MerzlyakImageTests(unittest.TestCase):
    def test_page_7_native_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = PipelineConfig(None, None, Path(tmp))
            img = get_page_image(MERZLYAK_PDF, 7, cfg)
            self.assertEqual((img.width, img.height), (886, 1329))   # як у pdfimages -list
            self.assertAlmostEqual(img.dpi, 152, delta=2)
            self.assertFalse(img.low_res)


if __name__ == "__main__":
    unittest.main()
