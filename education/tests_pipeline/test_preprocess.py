"""Тести для education.pdf_pipeline.ingest.preprocess."""
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from education.pdf_pipeline.ingest import preprocess as pp
from education.pdf_pipeline.config import PipelineConfig
from education.pdf_pipeline.datatypes import BBox, PageImage

ROOT = Path(__file__).resolve().parents[2]
MERZLYAK_PDF = ROOT / "5-klas-matematika-merzljak-2018-1-46.pdf"


def white(h=200, w=300, color=False):
    return np.full((h, w, 3) if color else (h, w), 255, dtype=np.uint8)


def text_like(h=400, w=600, angle=0.0):
    """Сіра «сторінка» з 8 чорними смугами-рядками, повернута на angle градусів."""
    img = white(h, w)
    for i in range(8):
        y = 60 + i * 35
        cv2.rectangle(img, (60, y), (540, y + 12), 0, -1)
    if angle:
        img, _ = pp.rotate(img, angle)
    return img


class TransformTests(unittest.TestCase):
    def test_identity(self):
        b = BBox(10, 20, 30, 40)
        self.assertEqual(pp.Transform().to_original(b), b)

    def test_upscale_then_crop(self):
        t = pp.Transform().then(pp._scale_matrix(2)).then(pp._shift_matrix(-100, -50))
        # точка оригіналу (60, 40) → ×2 = (120, 80) → зсув = (20, 30)
        self.assertEqual(t.to_original(BBox(20, 30, 40, 50)), BBox(60, 40, 70, 50))

    def test_rotation_roundtrip_is_close(self):
        img = text_like()
        _, m = pp.rotate(img, 3.0)
        t = pp.Transform().then(m)
        original = BBox(100, 100, 200, 120)
        corners = np.array([[100, 100, 1], [200, 120, 1]], dtype=float).T
        xs, ys, _ = t.m @ corners                    # переводимо в повернуту картинку
        rotated_box = BBox(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        back = t.to_original(rotated_box)
        self.assertGreater(back.iou(original), 0.6)   # після повороту рамка трохи ширша — це нормально

    def test_roundtrip_dict(self):
        t = pp.Transform().then(pp._scale_matrix(3))
        self.assertEqual(pp.Transform.from_dict(t.to_dict()), t)


class StepTests(unittest.TestCase):
    def test_to_gray(self):
        self.assertEqual(pp.to_gray(white(color=True)).shape, (200, 300))
        self.assertEqual(pp.to_gray(white()).shape, (200, 300))

    def test_upscale(self):
        out, m = pp.upscale(white(), 2.0)
        self.assertEqual(out.shape, (400, 600))
        self.assertEqual(m[0, 0], 2.0)

    def test_denoise_reduces_noise(self):
        rng = np.random.default_rng(0)
        # Зерно скану ~ ±8 рівнів яскравості; h=10 розрахований саме на такий шум.
        noisy = np.clip(200 + rng.normal(0, 8, (100, 100)), 0, 255).astype(np.uint8)
        self.assertLess(pp.denoise(noisy).std(), noisy.std() / 2)

    def test_normalize_contrast_stretches_pale_image(self):
        pale = np.tile(np.linspace(150, 200, 200, dtype=np.uint8), (200, 1))
        out = pp.normalize_contrast(pale)
        self.assertGreater(int(out.max()) - int(out.min()), 50)

    def test_remove_color_background_keeps_colored_text(self):
        img = white(color=True)
        img[:, :150] = (200, 240, 255)       # BGR: пастельно-жовтий фон плашки
        img[50:60, 160:200] = (40, 40, 220)  # BGR: насичений червоний «текст»
        img[100:110, 160:200] = (0, 0, 0)    # чорний текст
        out = pp.remove_color_background(img)
        self.assertEqual(tuple(out[10, 10]), (255, 255, 255))   # фон став білим
        self.assertEqual(tuple(out[55, 170]), (40, 40, 220))    # червоний текст на місці
        self.assertEqual(tuple(out[105, 170]), (0, 0, 0))       # чорний на місці

    def test_binarize_gives_only_black_and_white(self):
        img = text_like()
        for fn in (pp.binarize_otsu, pp.binarize_adaptive):
            with self.subTest(fn=fn.__name__):
                self.assertTrue(set(np.unique(fn(img))) <= {0, 255})

    def test_estimate_skew(self):
        for angle in (-3.0, 0.0, 2.0):
            with self.subTest(angle=angle):
                found = pp.estimate_skew(text_like(angle=angle))
                self.assertAlmostEqual(found, -angle, delta=0.5)   # щоб вирівняти — повернути назад

    def test_deskew_ignores_tiny_angle(self):
        img = text_like()
        out, m = pp.deskew(img)
        self.assertTrue(np.array_equal(out, img))
        self.assertTrue(np.allclose(m, np.eye(3)))

    def test_crop_margins(self):
        img = white(200, 300)
        img[50:60, 100:150] = 0
        out, m = pp.crop_margins(img, pad=5)
        self.assertEqual(out.shape, (20, 60))
        self.assertEqual((m[0, 2], m[1, 2]), (-95, -45))

    def test_crop_margins_blank_page(self):
        out, m = pp.crop_margins(white())
        self.assertEqual(out.shape, (200, 300))


class SpecTests(unittest.TestCase):
    def test_unknown_step(self):
        with self.assertRaises(ValueError):
            pp.step("magic")

    def test_cache_key_stable_and_sensitive(self):
        a = pp.PreprocessSpec("a", (pp.step("upscale", factor=2.0),))
        b = pp.PreprocessSpec("b", (pp.step("upscale", factor=2.0),))
        c = pp.PreprocessSpec("a", (pp.step("upscale", factor=3.0),))
        self.assertEqual(a.cache_key(), b.cache_key())      # назва не впливає
        self.assertNotEqual(a.cache_key(), c.cache_key())   # параметр впливає
        self.assertEqual(len(a.cache_key()), 12)

    def test_presets_have_different_keys(self):
        keys = {p.cache_key() for p in pp.PRESETS.values()}
        self.assertEqual(len(keys), len(pp.PRESETS))

    def test_apply_combines_transforms(self):
        spec = pp.PreprocessSpec("t", (pp.step("to_gray"), pp.step("upscale", factor=2.0),
                                       pp.step("crop_margins", pad=0)))
        img = white(100, 100, color=True)
        img[40:50, 30:60] = 0
        out, t = pp.apply(img, spec)
        # Бікубічне збільшення трохи «розмазує» край (±1 px), тому допускаємо невелику різницю.
        h, w = out.shape
        self.assertAlmostEqual(h, 20, delta=2)
        self.assertAlmostEqual(w, 60, delta=2)
        back = t.to_original(BBox(0, 0, w, h))
        expected = BBox(30, 40, 60, 50)
        for got, exp in zip(back.to_dict(), expected.to_dict()):
            self.assertAlmostEqual(got, exp, delta=1)   # кожна сторона — з точністю до 1 px

    def test_choose_preset(self):
        page = PageImage(1, Path("x/p-001.png"), 10, 10, 76.0, low_res=True)
        self.assertIs(pp.choose_preset(page), pp.PRESET_LOWRES)
        self.assertIs(pp.choose_preset(PageImage(1, Path("x"), 10, 10, 150.0)), pp.PRESET_DEFAULT)


class PreprocessPageTests(unittest.TestCase):
    def test_writes_and_reuses_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            pages_dir = Path(tmp) / "sha123" / "pages"
            src = pages_dir / "p-001.png"
            pp.save_image(src, text_like(100, 150))
            page = PageImage(1, src, 150, 100, 150.0)
            spec = pp.PreprocessSpec("t", (pp.step("upscale", factor=2.0),))

            first = pp.preprocess_page(page, spec)
            self.assertEqual(first.path, Path(tmp) / "sha123" / "prep" / spec.cache_key() / "p-001.png")
            self.assertEqual(pp.load_image(first.path).shape[:2], (200, 300))
            mtime = first.path.stat().st_mtime_ns

            second = pp.preprocess_page(page, spec)
            self.assertEqual(second, first)
            self.assertEqual(second.path.stat().st_mtime_ns, mtime)

    def test_unicode_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "сторінка" / "p.png"
            pp.save_image(path, white())
            self.assertEqual(pp.load_image(path).shape, (200, 300, 3))


@unittest.skipUnless(MERZLYAK_PDF.exists(), "немає PDF Мерзляка")
class RealPageTests(unittest.TestCase):
    def test_page_7_default_preset(self):
        from education.pdf_pipeline.ingest.images import get_page_image
        with tempfile.TemporaryDirectory() as tmp:
            page = get_page_image(MERZLYAK_PDF, 7, PipelineConfig(None, None, Path(tmp)))
            prepared = pp.preprocess_page(page)
            self.assertEqual(prepared.spec_name, "default")
            h, w = pp.load_image(prepared.path).shape[:2]
            self.assertAlmostEqual(w, page.width * 2, delta=2)
            self.assertAlmostEqual(h, page.height * 2, delta=2)


if __name__ == "__main__":
    unittest.main()
