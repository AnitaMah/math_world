"""Тести для education.pdf_pipeline.config."""
import dataclasses
import unittest
from pathlib import Path

from education.pdf_pipeline.config import DEFAULT_CACHE_DIR, PipelineConfig


class PipelineConfigTests(unittest.TestCase):
    def test_empty_environ_gives_defaults(self):
        cfg = PipelineConfig.from_env({})
        self.assertIsNone(cfg.tesseract_cmd)
        self.assertIsNone(cfg.tessdata_dir)
        self.assertEqual(cfg.cache_dir, DEFAULT_CACHE_DIR)

    def test_all_values_are_read(self):
        cfg = PipelineConfig.from_env({
            "TESSERACT_CMD": "C:/Program Files/Tesseract-OCR/tesseract.exe",
            "TESSDATA_PREFIX_BEST": "C:/tessdata_best",
            "PIPELINE_CACHE_DIR": "D:/cache",
        })
        self.assertEqual(cfg.tesseract_cmd, "C:/Program Files/Tesseract-OCR/tesseract.exe")
        self.assertIsInstance(cfg.tessdata_dir, Path)
        self.assertEqual(cfg.tessdata_dir, Path("C:/tessdata_best"))
        self.assertEqual(cfg.cache_dir, Path("D:/cache"))

    def test_empty_or_blank_value_becomes_none(self):
        cfg = PipelineConfig.from_env({"TESSERACT_CMD": "", "TESSDATA_PREFIX_BEST": "   "})
        self.assertIsNone(cfg.tesseract_cmd)
        self.assertIsNone(cfg.tessdata_dir)

    def test_config_is_frozen(self):
        cfg = PipelineConfig.from_env({})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            cfg.cache_dir = Path("x")  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
