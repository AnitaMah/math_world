"""Фаза 19: імпорт textbook.json у БД — ідемпотентність, dry-run, ручні правки, помилки."""
import copy
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from education.importers.textbook_json import TextbookImporter
from education.models import (
    Answer, ContentBlock, Exercise, Figure, Grade, ImportRun, Item, Paragraph, Section, Subject, SubExercise,
    Textbook,
)
from education.tests_pipeline.output.test_export import export, merzlyak_tree

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
       b"\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")
MEDIA = tempfile.mkdtemp(prefix="math_world_import_media_")


def fixture_json():
    """Мінімальний textbook.json (з тесту експорту): 1 розділ, § 1, пункт 1, 3 блоки, вправа №12 з 2 підпунктами."""
    return export(merzlyak_tree()[0])


def blocks_of(data):
    return data["sections"][0]["paragraphs"][0]["items"][0]["blocks"]


@override_settings(MEDIA_ROOT=MEDIA)
class ImporterTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "figs").mkdir()
        (self.tmp / "figs" / "p006_y300.png").write_bytes(PNG)
        self.data = fixture_json()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def imp(self, data=None, **kw):
        return TextbookImporter(data or self.data, base_dir=self.tmp, **kw).run()

    # ------------------------------------------------------------------ 0760
    def test_first_import_counts(self):
        res = self.imp()
        tb = Textbook.objects.get()
        self.assertEqual((tb.profile_code, tb.grade.number, tb.subject.code), ("math_merzlyak_5", 5, "math"))
        self.assertIn("Мерзляк", tb.author)
        self.assertEqual(Section.objects.get().name_uk, "Розділ I. Натуральні числа і дії з ними")
        self.assertEqual(Paragraph.objects.get().name_uk, "§ 1. Натуральні числа")
        self.assertEqual(Item.objects.get().content, "Ряд натуральних чисел")
        self.assertEqual(ContentBlock.objects.filter(item__isnull=False).count(), 2)
        self.assertEqual(ContentBlock.objects.get(paragraph__isnull=False).block_type, "self_test")
        ex = Exercise.objects.get()
        self.assertEqual((ex.number, ex.difficulty, ex.homework, ex.source_page), (12, "medium", True, 7))
        self.assertEqual([s.number for s in ex.subexercises.all()], ["1", "2"])
        self.assertEqual(ex.subexercises.get(number="1").answer_check, "verified")
        answers = {(a.subexercise.number if a.subexercise else None, a.kind): a.value_numeric for a in Answer.objects.all()}
        self.assertEqual(answers, {("1", "computed"): Decimal("673"), ("1", "book"): Decimal("673"),
                                   (None, "book"): None})
        fig = Figure.objects.get()
        self.assertTrue(fig.image.name.startswith("textbook_figures/"))
        self.assertEqual(list(ex.figures.all()), [fig])
        self.assertEqual(res.as_stats()["Exercise"]["created"], 1)
        run = ImportRun.objects.get()
        self.assertEqual((run.status, run.textbook, run.schema_version), ("success", tb, 1))

    # ------------------------------------------------------------------ 0761
    def test_second_import_all_unchanged(self):
        self.imp()
        res = self.imp()
        for model, counts in res.as_stats().items():
            with self.subTest(model=model):
                self.assertEqual(counts["created"] + counts["updated"] + counts["deleted"], 0, counts)
        self.assertEqual(Exercise.objects.count(), 1)
        self.assertEqual(ImportRun.objects.filter(status="success").count(), 2)

    def test_new_pdf_of_same_textbook_rebinds_instead_of_duplicating(self):
        """Повна книга замість стор. 1–46: інший sha PDF, але той самий підручник і ті самі дані."""
        self.imp()
        first = Textbook.objects.get()
        newer = copy.deepcopy(self.data)
        newer["meta"]["pdf_sha256"] = "b" * 64
        newer["meta"]["pdf_name"] = "5-klas-matematika-merzljak-2018.pdf"
        res = self.imp(newer)
        tb = Textbook.objects.get()                      # досі один підручник
        self.assertEqual((tb.pk, tb.pdf_sha256, tb.pdf_name), (first.pk, "b" * 64, newer["meta"]["pdf_name"]))
        self.assertTrue(any("перепідв" in w for w in res.warnings))
        self.assertEqual((Exercise.objects.count(), Section.objects.count()), (1, 1))

    def test_stale_item_not_in_json_is_pruned(self):
        """Пункт, що переїхав в інший параграф, не лишає по собі дубліката."""
        self.imp()
        keep = Item.objects.get()
        stale = Item.objects.create(paragraph=keep.paragraph, number=99, content="Застарілий")
        res = self.imp()
        self.assertFalse(Item.objects.filter(pk=stale.pk).exists())
        self.assertTrue(Item.objects.filter(pk=keep.pk).exists())
        self.assertEqual(res.as_stats()["Item"]["deleted"], 1)

    # ------------------------------------------------------------------ 0762
    def test_one_changed_exercise(self):
        self.imp()
        data = copy.deepcopy(self.data)
        blocks_of(data)[1]["exercises"][0]["condition"] = "Обчисліть усно:"
        res = self.imp(data)
        self.assertEqual(res.as_stats()["Exercise"]["updated"], 1)
        self.assertEqual(Exercise.objects.get().condition, "Обчисліть усно:")

    def test_removed_subexercise_deleted_and_new_exercise_keeps_old_ids(self):
        self.imp()
        old_pk = Exercise.objects.get().pk
        data = copy.deepcopy(self.data)
        ex = blocks_of(data)[1]["exercises"]
        ex[0]["subexercises"].pop()
        ex.insert(0, {**copy.deepcopy(ex[0]), "number": "11", "subexercises": [], "answer": {}, "figure_ids": []})
        res = self.imp(data)
        self.assertEqual(res.as_stats()["SubExercise"]["deleted"], 1)
        self.assertEqual(Exercise.objects.get(number=12).pk, old_pk)     # вставка перед нею не зсунула ключ

    # ------------------------------------------------------------------ 0763
    def test_dry_run_writes_nothing(self):
        models = (Textbook, Section, ContentBlock, Exercise, Figure, ImportRun, Subject, Grade)
        before = [m.objects.count() for m in models]          # Subject «math» створює міграція
        res = self.imp(dry_run=True)
        self.assertTrue(res.dry_run)
        self.assertEqual(res.as_stats()["Exercise"]["created"], 1)       # звіт є
        self.assertEqual([m.objects.count() for m in models], before)

    # ------------------------------------------------------------------ 0764
    def test_manual_edit_survives(self):
        self.imp()
        ex = Exercise.objects.get()
        ex.condition, ex.text_source = "Виправлено вчителем", "manual"
        ex.save()
        sub = SubExercise.objects.get(number="2")
        data = copy.deepcopy(self.data)
        blocks_of(data)[1]["exercises"][0]["condition"] = "Інший OCR"
        blocks_of(data)[1]["exercises"] = []                              # навіть якщо вправа зникла з JSON
        res = self.imp(data)
        ex.refresh_from_db()
        self.assertEqual(ex.condition, "Виправлено вчителем")
        self.assertTrue(SubExercise.objects.filter(pk=sub.pk).exists())
        self.assertEqual(res.as_stats()["Exercise"]["kept_manual"], 1)

    def test_manual_subexercise_survives(self):
        self.imp()
        SubExercise.objects.filter(number="2").update(text="98 · 34;", text_source="manual")
        data = copy.deepcopy(self.data)
        blocks_of(data)[1]["exercises"][0]["subexercises"][1]["text"] = "98: 34; (знову OCR)"
        self.imp(data)
        self.assertEqual(SubExercise.objects.get(number="2").text, "98 · 34;")

    # ------------------------------------------------------------------ 0765
    def test_invalid_json_rejected_db_untouched(self):
        bad = copy.deepcopy(self.data)
        blocks_of(bad)[0]["type"] = "no_such_block"
        with self.assertRaises(ValidationError):
            self.imp(bad)
        self.assertEqual(Textbook.objects.count() + ImportRun.objects.count(), 0)
        bad = copy.deepcopy(self.data)
        bad["schema_version"] = 99
        with self.assertRaisesRegex(ValidationError, "schema_version"):
            self.imp(bad)

    def test_failure_rolls_back_and_logs_failed_run(self):
        data = copy.deepcopy(self.data)
        importer = TextbookImporter(data, base_dir=self.tmp)

        def boom(*a, **k):
            raise RuntimeError("диск зник")
        importer._answers = boom
        with self.assertRaises(RuntimeError):
            importer.run()
        self.assertEqual(Textbook.objects.count() + Exercise.objects.count(), 0)
        run = ImportRun.objects.get()
        self.assertEqual(run.status, "failed")
        self.assertIn("диск зник", run.message)

    # ------------------------------------------------------------------ 0750: старі дані import_curriculum
    def test_existing_curriculum_items_reused(self):
        subject, _ = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})
        grade, _ = Grade.objects.get_or_create(subject=subject, number=5, defaults={"name_uk": "5 клас"})
        sec = Section.objects.create(grade=grade, number=1, name_uk="Розділ I. Натуральні числа і дії з ними")
        par = Paragraph.objects.create(section=sec, number=1, name_uk="§ 1. Натуральні числа")
        item = Item.objects.create(paragraph=par, number=1, content="Ряд натуральних чисел\n• додаткова примітка")
        old = ContentBlock.objects.create(item=item, block_type="theory", text="старий парсер", difficulty="medium")
        res = self.imp()
        self.assertEqual((Section.objects.count(), Paragraph.objects.count(), Item.objects.count()), (1, 1, 1))
        sec.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(sec.textbook.profile_code, "math_merzlyak_5")
        self.assertEqual(item.content, "Ряд натуральних чисел\n• додаткова примітка")   # назву не чіпаємо
        old.refresh_from_db()                                              # старий блок теорії оновлено, не задубльовано
        self.assertEqual((old.text, old.difficulty), ("Числа 1, 2, 3, … називають натуральними.", None))
        self.assertEqual(res.warnings, [])

    def test_title_conflict_is_warning(self):
        subject, _ = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})
        grade, _ = Grade.objects.get_or_create(subject=subject, number=5, defaults={"name_uk": "5 клас"})
        sec = Section.objects.create(grade=grade, number=1, name_uk="Розділ I. Натуральні числа і дії з ними")
        par = Paragraph.objects.create(section=sec, number=1, name_uk="§ 1. Натуральні числа")
        Item.objects.create(paragraph=par, number=1, content="Зовсім інша тема")
        res = self.imp()
        self.assertEqual(len(res.warnings), 1)
        self.assertIn("пункт 1", res.warnings[0])

    def test_duplicate_numbers_kept_and_idempotent(self):
        data = copy.deepcopy(self.data)
        ex = blocks_of(data)[1]["exercises"][0]
        ex["subexercises"].append({**ex["subexercises"][0], "text": "дубль OCR"})          # два підпункти «1»
        blocks_of(data)[1]["exercises"].append(copy.deepcopy(ex))                          # дві вправи №12
        self.imp(data)
        self.assertEqual(Exercise.objects.filter(number=12).count(), 2)
        self.assertEqual(SubExercise.objects.filter(number="1").count(), 4)
        res = self.imp(data)
        for model, counts in res.as_stats().items():
            self.assertEqual(counts["created"] + counts["updated"] + counts["deleted"], 0, (model, counts))

    def test_missing_figure_file_is_warning(self):
        (self.tmp / "figs" / "p006_y300.png").unlink()
        res = self.imp()
        self.assertTrue(any("p006_y300" in w for w in res.warnings))
        self.assertFalse(Figure.objects.get().image)

    def test_reset_recreates_blocks(self):
        self.imp()
        res = self.imp(reset=True)
        self.assertEqual(res.as_stats()["ContentBlock"]["deleted"], 3)
        self.assertEqual(ContentBlock.objects.count(), 3)
