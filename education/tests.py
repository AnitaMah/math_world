from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from education.models import Grade, Item, Paragraph, Section, Subject
from education.parsing.content_classifier import find_review_exercise_blocks
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


class ImportCurriculumGrade6TarasenkovaTests(TestCase):
    """
    Exercises import_curriculum against data/6_class_ukr.txt -- grade 6's
    Tarasenkova textbook, using the math_tarasenkova profile (Розділ uses
    Arabic numerals, unlike Merzlyak's Roman numerals -- see Step 35/36
    of the refactor plan). This file only has Розділ/§ headings, no
    individual lesson titles: Tarasenkova's real table of contents (PDF
    pages 303-304) doesn't list lesson titles the way Merzlyak's does, so
    Item rows are intentionally empty for now, pending a later step that
    extracts them from each §'s actual pages.
    """

    def setUp(self):
        self.sample_file = Path(settings.BASE_DIR) / "data" / "6_class_ukr.txt"

    def test_import_creates_sections_and_paragraphs_with_no_items_yet(self):
        call_command(
            "import_curriculum",
            "--file",
            str(self.sample_file),
            "--grade",
            "6",
            "--language",
            "uk",
            "--subject",
            "math_tarasenkova",
            "--subject-code",
            "math",
        )

        grade = Grade.objects.get(number=6, subject__code="math")
        self.assertEqual(Section.objects.filter(grade=grade).count(), 5)
        self.assertEqual(Paragraph.objects.filter(section__grade=grade).count(), 35)
        self.assertEqual(Item.objects.filter(paragraph__section__grade=grade).count(), 0)

    def test_grade_6_and_grade_5_coexist_under_the_same_math_subject(self):
        call_command(
            "import_curriculum",
            "--file",
            str(Path(settings.BASE_DIR) / "data" / "5_class_ukr.txt"),
            "--grade",
            "5",
            "--language",
            "uk",
        )
        call_command(
            "import_curriculum",
            "--file",
            str(self.sample_file),
            "--grade",
            "6",
            "--language",
            "uk",
            "--subject",
            "math_tarasenkova",
            "--subject-code",
            "math",
        )

        math_subject = Subject.objects.get(code="math")
        self.assertEqual(Grade.objects.filter(subject=math_subject).count(), 2)
        self.assertTrue(Grade.objects.filter(number=5, subject=math_subject).exists())
        self.assertTrue(Grade.objects.filter(number=6, subject=math_subject).exists())


class ContentClassifierTests(TestCase):
    """
    Step 15: find_review_exercise_blocks() against real OCR'd text from
    review/section_1_text/combined.txt (§1 of the grade-5 Merzlyak book,
    pages 5-15) -- not synthetic fixtures, so this tests against actual
    OCR noise, not an idealized version of it.
    """

    # Verbatim excerpt: item 1's exercise list through its "Задача від
    # Мудрої Сови" marker (which has OCR garbage prepended, "зб ... ох |"
    # -- exactly the case that motivated using .search over .match for
    # end markers).
    ITEM_1_EXCERPT = """\
Вправи для повторення

12. Обчисліть:

1)238- 435; 4) 2000 - 546; 17) 98-34;
2) 4385 - 2697; 5) 3400 - 896; 8) 645 : 36.
3) 843 - 457; 6) 23 : 46;

13. Назва «Україна» вперше згадується в Київському літописі (за
Шатіївським списком) під 1187 роком на означення Переяслав-
ської, Київської і Чернігівської земель. Скільки років минуло
від першої літописної появи назви «Україна»?

зб Задача від Мудрої Сови ох |
"""

    # Verbatim excerpt: item 2's exercise list through its "Коли
    # зроблено уроки" marker (clean, no OCR garbage this time).
    ITEM_2_EXCERPT = """\
Вправи для повторення
37. Обчисліть:
1)24 564; 5) 407 - 306; 9) 1134 :42;
2) 1754-60; 6)852:6; 10) 3198 : 26;

38. Виконайте дії:
1)49-26:(54 - 27); 3) (801 - 316) - 29;
2)36:9-18-:5; 4) (488 -- 808): 18.

Коли зроблено уроки
Як рахували в давнину
"""

    def test_finds_review_exercise_block_ending_at_garbled_wise_owl_marker(self):
        blocks = find_review_exercise_blocks(self.ITEM_1_EXCERPT)
        self.assertEqual(len(blocks), 1)
        self.assertIn("12. Обчисліть", blocks[0].text)
        self.assertIn("13. Назва", blocks[0].text)
        # The garbled marker line itself must not leak into the captured
        # block -- it's where the block ends, not part of it.
        self.assertNotIn("Мудрої Сови", blocks[0].text)

    def test_finds_review_exercise_block_ending_at_history_aside_marker(self):
        blocks = find_review_exercise_blocks(self.ITEM_2_EXCERPT)
        self.assertEqual(len(blocks), 1)
        self.assertIn("37. Обчисліть", blocks[0].text)
        self.assertIn("38. Виконайте дії", blocks[0].text)
        self.assertNotIn("Коли зроблено уроки", blocks[0].text)

    def test_finds_both_blocks_when_concatenated(self):
        combined = self.ITEM_1_EXCERPT + "\n" + self.ITEM_2_EXCERPT
        blocks = find_review_exercise_blocks(combined)
        self.assertEqual(len(blocks), 2)

    def test_no_marker_means_no_blocks(self):
        self.assertEqual(find_review_exercise_blocks("Просто якийсь текст."), [])


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
