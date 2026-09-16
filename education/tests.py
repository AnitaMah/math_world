from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from education.models import Grade, Item, Paragraph, Section, Subject
from education.parsing.math_heuristic import annotate_blocks, needs_vision_ocr


class ImportCurriculumCommandTests(TestCase):
    """
    Exercises the import_curriculum command (education/management/commands/
    import_curriculum.py) against data/5_class_ukr.txt -- the real 5th-grade
    math table of contents, corrected to include the "Коли зроблено уроки"
    historical aside that earlier copies of this file were missing (see the
    refactor plan for how that gap was found by cross-checking the source
    PDF).
    """

    def setUp(self):
        self.sample_file = Path(settings.BASE_DIR) / "data" / "5_class_ukr.txt"

    def test_import_creates_full_hierarchy(self):
        call_command(
            "import_curriculum",
            "--file",
            str(self.sample_file),
            "--grade",
            "5",
            "--language",
            "uk",
        )

        grade = Grade.objects.get(number=5)
        self.assertEqual(grade.name_uk, "5 клас")
        self.assertEqual(Section.objects.filter(grade=grade).count(), 2)
        self.assertEqual(Paragraph.objects.filter(section__grade=grade).count(), 5)
        self.assertEqual(Item.objects.filter(paragraph__section__grade=grade).count(), 38)

    def test_import_merges_historical_aside_into_owning_item(self):
        call_command(
            "import_curriculum",
            "--file",
            str(self.sample_file),
            "--grade",
            "5",
            "--language",
            "uk",
        )

        # The "• Від ліктів та долонь до метричної системи" aside sits
        # directly under item 3 ("Відрізок. Довжина відрізка") in the real
        # textbook, not under item 2 -- it must be merged into item 3's
        # content rather than becoming its own row or being dropped.
        third_item = Item.objects.get(paragraph__section__grade__number=5, number=3)
        self.assertTrue(third_item.content.startswith("Відрізок. Довжина відрізка"))
        self.assertIn("Від ліктів та долонь до метричної системи", third_item.content)

    def test_import_skips_administrative_and_noise_lines(self):
        call_command(
            "import_curriculum",
            "--file",
            str(self.sample_file),
            "--grade",
            "5",
            "--language",
            "uk",
        )

        all_content = "\n".join(
            Item.objects.filter(paragraph__section__grade__number=5).values_list(
                "content", flat=True
            )
        )
        self.assertNotIn("Завдання №", all_content)
        self.assertNotIn("Головне в параграфі", all_content)
        self.assertNotIn("Зміст 271", all_content)

    def test_reset_flag_removes_previous_grade_content_before_import(self):
        math_subject, _ = Subject.objects.get_or_create(
            code="math", defaults={"name_uk": "Математика"}
        )
        grade = Grade.objects.create(number=5, subject=math_subject, name_uk="5 клас")
        section = Section.objects.create(grade=grade, number=99, name_uk="Старий розділ")
        paragraph = Paragraph.objects.create(section=section, number=1, name_uk="Старий параграф")
        Item.objects.create(paragraph=paragraph, number=1, content="Старий пункт")

        call_command(
            "import_curriculum",
            "--file",
            str(self.sample_file),
            "--grade",
            "5",
            "--language",
            "uk",
            "--reset",
        )

        grade = Grade.objects.get(number=5)
        self.assertEqual(Section.objects.filter(grade=grade).count(), 2)
        self.assertFalse(Section.objects.filter(grade=grade, number=99).exists())
        self.assertEqual(Paragraph.objects.filter(section__grade=grade).count(), 5)
        self.assertEqual(Item.objects.filter(paragraph__section__grade=grade).count(), 38)


class MathHeuristicTests(TestCase):
    """
    Step 28: the local (no API calls) heuristic that flags which OCR'd
    blocks likely contain mangled math notation, so Step 29's Gemini
    vision OCR only gets spent on those -- kept conservative on purpose,
    since every false positive costs a rate-limited API call later.
    """

    def test_plain_ukrainian_prose_is_not_flagged(self):
        text = (
            "Дріб — це число, яке показує частину від цілого. "
            "Знаменник показує, на скільки частин поділили ціле."
        )
        self.assertFalse(needs_vision_ocr(text))

    def test_explicit_instruction_marker_is_flagged(self):
        text = "Обчисліть периметр трикутника зі сторонами 3 см, 4 см і 5 см."
        self.assertTrue(needs_vision_ocr(text))

    def test_math_symbols_are_flagged(self):
        text = "Розв'яжи: x + 5 = 12, знайди значення x."
        self.assertTrue(needs_vision_ocr(text))

    def test_garbled_fraction_fragments_are_flagged(self):
        # Simulates what Tesseract tends to produce when it hits a
        # fraction it can't read cleanly -- lots of short isolated
        # digit/symbol tokens instead of a normal sentence.
        text = "1 / 2 + 3 = . 4 5"
        self.assertTrue(needs_vision_ocr(text))

    def test_empty_text_is_not_flagged(self):
        self.assertFalse(needs_vision_ocr(""))
        self.assertFalse(needs_vision_ocr("   "))

    def test_annotate_blocks_adds_flag_to_each_block(self):
        blocks = [
            {"text": "Просте речення без математики."},
            {"text": "Обчисліть площу прямокутника."},
        ]
        annotated = annotate_blocks(blocks)
        self.assertFalse(annotated[0]["needs_vision_ocr"])
        self.assertTrue(annotated[1]["needs_vision_ocr"])
