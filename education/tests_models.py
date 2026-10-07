"""Фаза 18: моделі для імпорту підручників (Textbook, Exercise, SubExercise, Answer, Figure, ImportRun)."""
import shutil
import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from .models import (
    DIFFICULTY_CHOICES, TEXT_SOURCE_CHOICES, Answer, ContentBlock, Exercise, Figure, Grade, ImportRun, Item,
    Paragraph, Section, SubExercise, Subject, Textbook, parse_answer_number,
)


def make_textbook(sha="a" * 64):
    subject, _ = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})
    grade, _ = Grade.objects.get_or_create(subject=subject, number=5, defaults={"name_uk": "5 клас"})
    return Textbook.objects.create(subject=subject, grade=grade, profile_code="math_merzlyak_5",
                                   title="Математика. 5 клас", author="Мерзляк", year=2018, pdf_sha256=sha)


class TreeMixin:
    def setUp(self):
        self.tb = make_textbook()
        self.section = Section.objects.create(grade=self.tb.grade, textbook=self.tb, number=1, name_uk="Натуральні числа")
        self.par = Paragraph.objects.create(section=self.section, number=1, name_uk="Натуральні числа")
        self.item = Item.objects.create(paragraph=self.par, number=1, content="Ряд натуральних чисел")
        self.block = ContentBlock.objects.create(item=self.item, block_type="exercise", order=1)


class TextbookTests(TreeMixin, TestCase):
    def test_str_and_relations(self):
        self.assertEqual(str(self.tb), "Математика. 5 клас (Мерзляк)")
        self.assertEqual(list(self.tb.sections.all()), [self.section])

    def test_sha_unique(self):
        with self.assertRaises(IntegrityError):
            make_textbook()

    def test_old_sections_without_textbook_allowed(self):
        Section.objects.create(grade=self.tb.grade, number=2, name_uk="Старий імпорт")

    def test_delete_textbook_cascades(self):
        ex = Exercise.objects.create(textbook=self.tb, block=self.block, number=1)
        self.tb.delete()
        self.assertFalse(Exercise.objects.filter(pk=ex.pk).exists())
        self.assertFalse(Section.objects.filter(pk=self.section.pk).exists())


class ContentBlockTests(TreeMixin, TestCase):
    def test_paragraph_level_block(self):
        b = ContentBlock.objects.create(paragraph=self.par, block_type="self_test")
        self.assertEqual(b.lesson, self.par)
        self.assertIn(b, self.par.content_blocks.all())

    def test_needs_exactly_one_parent(self):
        for kwargs in ({}, {"item": self.item, "paragraph": self.par}):
            with self.subTest(kwargs=list(kwargs)), self.assertRaises(IntegrityError), transaction.atomic():
                ContentBlock.objects.create(block_type="theory", **kwargs)

    def test_source_fields(self):
        b = ContentBlock.objects.create(item=self.item, block_type="theory", source_page=7,
                                        source_bbox=[70, 100, 700, 140], needs_review=True, text_source="vision")
        b.refresh_from_db()
        self.assertEqual((b.source_bbox, b.get_text_source_display()), ([70, 100, 700, 140], "Vision-LLM"))


class ExerciseTests(TreeMixin, TestCase):
    def test_subexercises_ordering_and_cascade(self):
        ex = Exercise.objects.create(textbook=self.tb, block=self.block, number=12, difficulty="medium")
        for order, (n, text) in enumerate([("2", "4385 + 2697"), ("1", "238 + 435"), ("10", "1 + 1")]):
            SubExercise.objects.create(exercise=ex, number=n, order=[1, 0, 2][order], text=text, expr_status="ok")
        self.assertEqual([s.number for s in ex.subexercises.all()], ["1", "2", "10"])
        self.assertTrue(ex.subexercises.first().expr_well_formed)
        ex.delete()
        self.assertEqual(SubExercise.objects.count(), 0)

    def test_oral_numbers_may_repeat(self):
        oral = ContentBlock.objects.create(item=self.item, block_type="oral_exercise", order=0)
        Exercise.objects.create(textbook=self.tb, block=oral, number=1)
        Exercise.objects.create(textbook=self.tb, block=self.block, number=1)
        self.assertEqual(Exercise.objects.filter(textbook=self.tb, number=1).count(), 2)
        self.assertEqual(str(oral.exercises.get()), "№1 (усна)")

    def test_figures_m2m(self):
        ex = Exercise.objects.create(textbook=self.tb, block=self.block, number=45)
        fig = Figure.objects.create(textbook=self.tb, figure_id="p020_y300", number="15", source_page=20)
        ex.figures.add(fig)
        self.block.figures.add(fig)
        self.assertEqual(list(fig.exercises.all()), [ex])
        self.assertEqual(str(fig), "Рис. 15")


class AnswerTests(TreeMixin, TestCase):
    def test_parse_answer_number(self):
        cases = {"-3,5": Decimal("-3.5"), "− 76": Decimal("-76"), "1454": Decimal("1454"), "80,09": Decimal("80.09"),
                 "3/4": Decimal("0.75"), "2 1/3": Decimal("2.333333"), "так": None, "12; 16": None, "": None, "1/0": None}
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_answer_number(text), expected)

    def test_value_numeric_filled_on_save(self):
        ex = Exercise.objects.create(textbook=self.tb, block=self.block, number=1125)
        sub = SubExercise.objects.create(exercise=ex, number="6", text="…")
        a = Answer.objects.create(exercise=ex, subexercise=sub, kind="book", text="-3,1")
        a.refresh_from_db()
        self.assertEqual(a.value_numeric, Decimal("-3.1"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Answer.objects.create(exercise=ex, subexercise=sub, kind="book", text="5")
        Answer.objects.create(exercise=ex, subexercise=sub, kind="computed", text="-3,1")


_MEDIA = tempfile.mkdtemp(prefix="math_world_media_")


@override_settings(MEDIA_ROOT=_MEDIA)
class FigureImageTests(TreeMixin, TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def test_image_upload_and_unique_id(self):
        png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
               b"\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")
        fig = Figure.objects.create(textbook=self.tb, figure_id="p006_y300",
                                    image=SimpleUploadedFile("p006_y300.png", png, content_type="image/png"))
        self.assertTrue(fig.image.name.startswith("textbook_figures/"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Figure.objects.create(textbook=self.tb, figure_id="p006_y300")


class ImportRunTests(TreeMixin, TestCase):
    def test_defaults_and_set_null(self):
        run = ImportRun.objects.create(textbook=self.tb, json_sha256="b" * 64, schema_version=1, stats={"exercises": 201})
        self.assertEqual(run.status, "running")
        self.tb.delete()
        run.refresh_from_db()
        self.assertIsNone(run.textbook)              # журнал лишається


class ChoicesMatchPipelineTests(TestCase):
    """Переліки Django і JSON-схеми пайплайна мають збігатися, інакше імпорт впаде на валідних даних."""

    def test_block_types(self):
        from education.pdf_pipeline.profiles import BLOCK_TYPES
        self.assertEqual({c for c, _ in ContentBlock.BLOCK_TYPE_CHOICES}, set(BLOCK_TYPES))

    def test_difficulty(self):
        from education.pdf_pipeline.profiles import DIFFICULTY_LEVELS
        self.assertEqual({c for c, _ in DIFFICULTY_CHOICES}, {*DIFFICULTY_LEVELS, "unknown"})

    def test_text_source_and_expr_status(self):
        from education.pdf_pipeline.schema import DEFINITIONS
        self.assertEqual({c for c, _ in TEXT_SOURCE_CHOICES}, set(DEFINITIONS["text_source"]["enum"]))
        statuses = {s for s in DEFINITIONS["subexercise"]["properties"]["expr_status"]["enum"] if s}
        self.assertEqual({c for c, _ in SubExercise.EXPR_STATUS_CHOICES}, statuses)
