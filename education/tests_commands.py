"""Фаза 20: management-команди parse_textbook, import_textbook, textbook_status, черга перевірки."""
import csv
import io
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from education.management.commands.parse_textbook import Command as ParseCommand
from education.models import Answer, Exercise, ImportRun, SubExercise, Textbook
from education.tests_pipeline.test_export import export, merzlyak_tree
from education.tests_pipeline.test_run import PagedFakeOcr, make_pdf

MEDIA = tempfile.mkdtemp(prefix="math_world_cmd_media_")


def run(*args, **kwargs):
    out = io.StringIO()
    call_command(*args, stdout=out, **kwargs)
    return out.getvalue()


@override_settings(MEDIA_ROOT=MEDIA)
class CommandTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.json = self.tmp / "textbook.json"
        self.json.write_text(json.dumps(export(merzlyak_tree()[0]), ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------ parse_textbook
    def test_parse_textbook_with_fake_ocr(self):
        pdf = self.tmp / "book.pdf"
        make_pdf(pdf)
        engine = PagedFakeOcr()
        logging.getLogger("pdf_pipeline").disabled = True
        self.addCleanup(setattr, logging.getLogger("pdf_pipeline"), "disabled", False)
        with mock.patch.object(ParseCommand, "engine_factory", staticmethod(lambda cfg: engine)), \
                mock.patch.dict(os.environ, {"PIPELINE_CACHE_DIR": str(self.tmp / "cache")}):
            out = run("parse_textbook", "--profile", "math_merzlyak_5", "--pdf", str(pdf), "--pages", "5-7",
                      "--out", str(self.tmp / "out"))
        self.assertIn("textbook.json", out)
        self.assertIn("Сторінки з помилками: {7: 'ocr'}", out)
        self.assertTrue((self.tmp / "out" / "math_merzlyak_5" / "report.html").exists())
        self.assertEqual(sorted(set(engine.calls)), [5, 6, 7])

    def test_parse_textbook_errors(self):
        with self.assertRaisesRegex(CommandError, "Невідомий профіль"):
            run("parse_textbook", "--profile", "nope")
        with self.assertRaisesRegex(CommandError, "PDF не знайдено"):
            run("parse_textbook", "--profile", "math_merzlyak_5", "--pdf", str(self.tmp / "missing.pdf"))

    # ------------------------------------------------------------------ import_textbook
    def test_import_textbook_table_and_idempotent(self):
        out = run("import_textbook", "--json", str(self.json))
        self.assertIn("Exercise", out)
        self.assertIn("Готово: Textbook", out)
        self.assertEqual(Exercise.objects.count(), 1)
        out = run("import_textbook", "--json", str(self.json))
        exercise_row = next(line for line in out.splitlines() if line.startswith("Exercise"))
        self.assertEqual(exercise_row.split()[1:], ["0", "0", "0", "1", "0"])

    def test_import_textbook_dry_run(self):
        out = run("import_textbook", "--json", str(self.json), "--dry-run")
        self.assertIn("DRY-RUN", out)
        self.assertEqual(Textbook.objects.count() + ImportRun.objects.count(), 0)

    def test_import_textbook_errors_give_command_error(self):
        with self.assertRaisesRegex(CommandError, "не знайдено"):
            run("import_textbook", "--json", str(self.tmp / "nope.json"))
        bad = self.tmp / "bad.json"
        bad.write_text('{"schema_version": 1}', encoding="utf-8")
        with self.assertRaisesRegex(CommandError, "Невалідний JSON"):
            run("import_textbook", "--json", str(bad))

    # ------------------------------------------------------------------ textbook_status
    def test_textbook_status(self):
        self.assertIn("Підручників ще немає", run("textbook_status"))
        run("import_textbook", "--json", str(self.json))
        out = run("textbook_status")
        self.assertIn("math_merzlyak_5", out)
        self.assertIn("вправ: 1", out)
        self.assertIn("підпунктів: 2, на перевірку: 1, відповідь збіглась: 1", out)
        self.assertIn("Успішно", out)

    # ------------------------------------------------------------------ черга перевірки
    def test_review_queue_roundtrip(self):
        run("import_textbook", "--json", str(self.json))
        queue = self.tmp / "queue.csv"
        out = run("export_review_queue", "--textbook", "math_merzlyak_5", "--out", str(queue))
        self.assertIn("1 рядків", out)
        with queue.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual((rows[0]["kind"], rows[0]["sub"], rows[0]["text"]), ("subexercise", "2", "98: 34;"))
        self.assertIn("suspect", rows[0]["reason"])

        rows[0]["new_text"] = "98 · 34;"
        with queue.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        self.assertIn("DRY-RUN: виправлено 1", run("import_review_fixes", "--csv", str(queue), "--dry-run"))
        self.assertEqual(SubExercise.objects.get(number="2").text, "98: 34;")
        self.assertIn("виправлено 1", run("import_review_fixes", "--csv", str(queue)))
        sub = SubExercise.objects.get(number="2")
        self.assertEqual((sub.text, sub.text_source, sub.needs_review, sub.expr_status), ("98 · 34;", "manual", False, "ok"))
        self.assertEqual(Answer.objects.get(subexercise=sub, kind="computed").text, "3332")

        # повторний імпорт JSON не повертає OCR-текст
        run("import_textbook", "--json", str(self.json))
        self.assertEqual(SubExercise.objects.get(number="2").text, "98 · 34;")
        self.assertIn("0 рядків", run("export_review_queue", "--out", str(queue)))

    def test_review_fixes_reviewed_flag_and_bad_rows(self):
        run("import_textbook", "--json", str(self.json))
        sub = SubExercise.objects.get(number="2")
        queue = self.tmp / "fixes.csv"
        with queue.open("w", encoding="utf-8-sig", newline="") as fh:
            fh.write("kind,id,new_text,reviewed\n")
            fh.write(f"subexercise,{sub.pk},,так\n")
            fh.write("exercise,999999,Текст,\n")
            fh.write("exercise,1,,\n")
        out = run("import_review_fixes", "--csv", str(queue))
        self.assertIn("виправлено 0, підтверджено 1, пропущено 1, помилок 1", out)
        sub.refresh_from_db()
        self.assertEqual((sub.text, sub.text_source, sub.needs_review), ("98: 34;", "manual", False))

    def test_review_fixes_missing_columns(self):
        bad = self.tmp / "bad.csv"
        bad.write_text("id,text\n1,x\n", encoding="utf-8")
        with self.assertRaisesRegex(CommandError, "немає колонок"):
            run("import_review_fixes", "--csv", str(bad))
