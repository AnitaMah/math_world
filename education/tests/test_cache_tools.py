"""0872: clean_pipeline_cache."""
import io
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from education import cache_tools as ct
from education.models import Grade, Subject, Textbook

KNOWN, UNKNOWN = "a" * 64, "b" * 64


def fill(path: Path, size: int):
    path.mkdir(parents=True, exist_ok=True)
    (path / "x.bin").write_bytes(b"0" * size)


class CacheToolsTests(TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        for sha in (KNOWN, UNKNOWN):
            for part, size in (("pages", 1000), ("prep", 5000), ("ocr", 300)):
                fill(self.root / sha / part, size)
        fill(self.root / "vision", 70)
        subject, _ = Subject.objects.get_or_create(code="math", defaults={"name_uk": "М"})
        grade, _ = Grade.objects.get_or_create(subject=subject, number=5)
        Textbook.objects.create(subject=subject, grade=grade, profile_code="math_merzlyak_5", title="T", pdf_sha256=KNOWN)
        cfg = mock.Mock(cache_dir=self.root)
        p = mock.patch("education.management.commands.clean_pipeline_cache.PipelineConfig.from_env_file", return_value=cfg)
        p.start()
        self.addCleanup(p.stop)

    def run_cmd(self, *args):
        out = io.StringIO()
        call_command("clean_pipeline_cache", *args, stdout=out)
        return out.getvalue()

    def exists(self, sha, part):
        return (self.root / sha / part).exists()

    def test_scan_sizes_and_labels(self):
        entries = ct.scan(self.root, {KNOWN: "math_merzlyak_5"})
        by = {e.sha: e for e in entries}
        self.assertEqual(by[KNOWN].sizes, {"pages": 1000, "prep": 5000, "ocr": 300})
        self.assertEqual((by[KNOWN].label, by[UNKNOWN].known), ("math_merzlyak_5", False))
        self.assertEqual(ct.other_size(self.root, entries), 70)             # vision/ не вважається кешем PDF

    def test_default_run_deletes_nothing(self):
        out = self.run_cmd()
        self.assertIn("math_merzlyak_5", out)
        self.assertIn("Нічого не видалено", out)
        self.assertIn("пропущено", out)
        self.assertTrue(all(self.exists(s, p) for s in (KNOWN, UNKNOWN) for p in ct.PARTS))

    def test_yes_clears_only_prep_of_known(self):
        out = self.run_cmd("--yes")
        self.assertIn("Звільнено 4.9 КБ", out)
        self.assertFalse(self.exists(KNOWN, "prep"))
        self.assertTrue(self.exists(KNOWN, "pages") and self.exists(KNOWN, "ocr"))
        self.assertTrue(self.exists(UNKNOWN, "prep"))                       # кеш без запису в БД не чіпаємо
        self.assertTrue((self.root / "vision").exists())

    def test_parts_and_include_unknown(self):
        self.run_cmd("--parts", "prep,pages", "--include-unknown", "--yes")
        for sha in (KNOWN, UNKNOWN):
            self.assertFalse(self.exists(sha, "prep") or self.exists(sha, "pages"))
            self.assertTrue(self.exists(sha, "ocr"))                        # ocr лишається, бо не просили
        self.assertTrue((self.root / "vision" / "x.bin").exists())

    def test_bad_parts_and_missing_cache(self):
        with self.assertRaises(CommandError):
            self.run_cmd("--parts", "vision")
        shutil.rmtree(self.root)
        self.assertIn("Кешу немає", self.run_cmd())

    def test_human(self):
        self.assertEqual((ct.human(512), ct.human(2048), ct.human(5 * 1024 ** 2)), ("512 Б", "2.0 КБ", "5.0 МБ"))
