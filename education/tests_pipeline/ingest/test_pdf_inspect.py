"""Тести для education.pdf_pipeline.ingest.pdf_inspect."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pymupdf

from education.pdf_pipeline.ingest.pdf_inspect import (
    PageInspection, PdfKind, classify_pdf, cyrillic_ratio, inspect_pdf,
    mixed_script_words, pdf_sha256, save_inspection, text_layer_quality,
)

ROOT = Path(__file__).resolve().parents[3]
MERZLYAK_PDF = ROOT / "5-klas-matematika-merzljak-2018-1-46.pdf"


def make_born_digital_pdf(path: Path) -> None:
    """PDF зі справжнім текстом (як з Word)."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello, this is real text", fontsize=12)
    doc.save(path)


def make_scan_pdf(path: Path, px: tuple[int, int] = (200, 300), pt: tuple[int, int] = (144, 216)) -> None:
    """PDF, де сторінка — одна картинка на весь розмір (як скан). Без тексту."""
    doc = pymupdf.open()
    page = doc.new_page(width=pt[0], height=pt[1])
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, *px), False)
    pix.clear_with(255)
    page.insert_image(page.rect, pixmap=pix)
    doc.save(path)


def page_info(**overrides) -> PageInspection:
    """PageInspection з типовими значеннями «скан без тексту»; поля можна перевизначити."""
    base = dict(pdf_page=1, width_pt=400.0, height_pt=600.0, fonts=(), n_images=1,
                max_ppi=150.0, image_coverage=1.0, text_chars=0, text_quality=0.0)
    base.update(overrides)
    return PageInspection(**base)


class TextQualityTests(unittest.TestCase):
    def test_cyrillic_ratio(self):
        self.assertEqual(cyrillic_ratio("Вправи"), 1.0)
        self.assertEqual(cyrillic_ratio("abc"), 0.0)
        self.assertEqual(cyrillic_ratio("123 !"), 0.0)

    def test_mixed_words(self):
        # "Bправи" і "нaтуральний" містять латинські B / a серед кирилиці.
        # "cBoei" і "Bech" — повністю латинські, тому мішаними НЕ вважаються.
        text = "своєї cBoei Bправи нaтуральний весь Bech"
        self.assertEqual(mixed_script_words(text), ["Bправи", "нaтуральний"])

    def test_all_latin_lookalike_words_lower_cyrillic_ratio(self):
        self.assertLess(cyrillic_ratio("своєї cBoei"), 0.6)

    def test_clean_ukrainian_is_high(self):
        self.assertGreater(text_layer_quality("Записати весь натуральний ряд неможливо."), 0.95)

    def test_lookalikes_lower_quality(self):
        clean = text_layer_quality("Записати весь натуральний ряд")
        broken = text_layer_quality("Записати Bech натуральний ряд")
        self.assertLess(broken, clean)
        self.assertLess(broken, 0.9)

    def test_mixed_words_lower_quality(self):
        self.assertLess(text_layer_quality("Bправи нaтуральний ряд"), 0.5)

    def test_empty_is_zero(self):
        self.assertEqual(text_layer_quality(""), 0.0)
        self.assertEqual(text_layer_quality("12 + 5 = 17"), 0.0)


class PageCategoryTests(unittest.TestCase):
    def test_scan_only(self):
        self.assertEqual(page_info().category, "scan_only")

    def test_scan_with_ocr_layer(self):
        p = page_info(fonts=("GlyphLessFont",), text_chars=500, text_quality=0.9)
        self.assertTrue(p.has_glyphless)
        self.assertEqual(p.category, "scan_with_ocr_layer")

    def test_born_digital(self):
        p = page_info(fonts=("Times",), n_images=0, max_ppi=None, image_coverage=0.0, text_chars=800)
        self.assertEqual(p.category, "born_digital")

    def test_empty(self):
        p = page_info(n_images=0, max_ppi=None, image_coverage=0.0)
        self.assertEqual(p.category, "empty")

    def test_small_picture_with_text_is_born_digital(self):
        p = page_info(fonts=("Arial",), image_coverage=0.2, text_chars=300)
        self.assertEqual(p.category, "born_digital")


class ClassifyPdfTests(unittest.TestCase):
    def test_all_same(self):
        self.assertEqual(classify_pdf([page_info(), page_info(pdf_page=2)]), PdfKind.SCAN_ONLY)

    def test_empty_pages_are_ignored(self):
        blank = page_info(n_images=0, max_ppi=None, image_coverage=0.0)
        self.assertEqual(classify_pdf([page_info(), blank]), PdfKind.SCAN_ONLY)

    def test_mixed(self):
        digital = page_info(fonts=("Times",), n_images=0, max_ppi=None, image_coverage=0.0, text_chars=10)
        self.assertEqual(classify_pdf([page_info(), digital]), PdfKind.MIXED)

    def test_nothing(self):
        self.assertEqual(classify_pdf([]), PdfKind.EMPTY)


class SyntheticPdfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sha256_matches_hashlib(self):
        path = self.dir / "a.pdf"
        make_born_digital_pdf(path)
        self.assertEqual(pdf_sha256(path, chunk_size=7), hashlib.sha256(path.read_bytes()).hexdigest())

    def test_born_digital(self):
        path = self.dir / "digital.pdf"
        make_born_digital_pdf(path)
        result = inspect_pdf(path)
        self.assertEqual(result.kind, PdfKind.BORN_DIGITAL)
        self.assertIsNone(result.median_ppi)

    def test_scan_only_and_ppi(self):
        path = self.dir / "scan.pdf"
        make_scan_pdf(path, px=(200, 300), pt=(144, 216))   # 200 px на 2 дюйми = 100 ppi
        result = inspect_pdf(path)
        self.assertEqual(result.kind, PdfKind.SCAN_ONLY)
        self.assertAlmostEqual(result.pages[0].max_ppi, 100.0, delta=1)
        self.assertEqual(result.low_res_pages, (1,))

    def test_high_res_scan_is_not_low_res(self):
        path = self.dir / "scan300.pdf"
        make_scan_pdf(path, px=(600, 900), pt=(144, 216))   # 300 ppi
        self.assertEqual(inspect_pdf(path).low_res_pages, ())

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            inspect_pdf(self.dir / "nope.pdf")

    def test_bad_page_number(self):
        path = self.dir / "scan.pdf"
        make_scan_pdf(path)
        with self.assertRaises(ValueError):
            inspect_pdf(path, pages=[2])

    def test_save_inspection_writes_json(self):
        path = self.dir / "scan.pdf"
        make_scan_pdf(path)
        result = inspect_pdf(path)
        out = save_inspection(result, self.dir / "cache")
        self.assertEqual(out, self.dir / "cache" / result.sha256 / "inspect.json")
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["kind"], "scan_only")
        self.assertEqual(data["pages"][0]["category"], "scan_only")


@unittest.skipUnless(MERZLYAK_PDF.exists(), "немає PDF Мерзляка")
class MerzlyakRealPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = inspect_pdf(MERZLYAK_PDF, pages=[5, 7])

    def test_kind(self):
        self.assertEqual(self.result.kind, PdfKind.SCAN_WITH_OCR_LAYER)

    def test_ppi_about_152(self):
        self.assertAlmostEqual(self.result.median_ppi, 152, delta=3)
        self.assertEqual(self.result.low_res_pages, ())

    def test_page_count_is_whole_book(self):
        self.assertEqual(self.result.page_count, 46)
        self.assertEqual([p.pdf_page for p in self.result.pages], [5, 7])


if __name__ == "__main__":
    unittest.main()
