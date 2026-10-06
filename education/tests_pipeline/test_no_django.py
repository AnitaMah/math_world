"""Пакет pdf_pipeline не повинен залежати від Django."""
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent / "pdf_pipeline"
FORBIDDEN_PREFIXES = ("import django", "from django")


def find_django_imports(root: Path) -> list[str]:
    """Повертає список 'файл:рядок' з імпортами Django у всіх .py під root."""
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith(FORBIDDEN_PREFIXES):
                found.append(f"{path.relative_to(root)}:{number}: {line.strip()}")
    return found


class NoDjangoInPipelineTests(unittest.TestCase):
    def test_pipeline_package_exists(self):
        self.assertTrue(PIPELINE_DIR.is_dir(), PIPELINE_DIR)

    def test_no_django_imports(self):
        found = find_django_imports(PIPELINE_DIR)
        self.assertEqual(found, [], "Django імпортовано в pdf_pipeline:\n" + "\n".join(found))

    def test_detector_catches_indented_import(self):
        # Перевіряємо сам детектор на тимчасовому файлі.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.py"
            bad.write_text("def f():\n    from django.db import models\n", encoding="utf-8")
            self.assertEqual(len(find_django_imports(Path(tmp))), 1)


if __name__ == "__main__":
    unittest.main()
