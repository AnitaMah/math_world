from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from education.models import Grade, Item, Paragraph, Section, Subject


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


class TarasenkovaTocPagesTests(TestCase):
    """
    Step 36 prep: data/tarasenkova_toc_pages.py was transcribed by eye
    from the book's own Зміст (its dotted leaders defeat Tesseract), in
    a font where "3" and "8" are easy to confuse. The main defense against
    a transcription mistake is that page numbers must strictly increase
    all the way through the book -- this test enforces that mechanically,
    the same cross-check that already caught two real misreads by hand
    (see the module's own CONFIDENCE NOTE).
    """

    def test_paragraph_pages_strictly_increase_through_the_whole_book(self):
        from data.tarasenkova_toc_pages import PARAGRAPH_PAGES

        pages = [p.start_page for p in PARAGRAPH_PAGES]
        self.assertEqual(
            pages,
            sorted(pages),
            "§ start pages must strictly increase -- a misread digit "
            "(e.g. '3' read as '8' in this book's Зміст font) breaks this.",
        )
        self.assertEqual(len(pages), len(set(pages)), "no two §s share a start page")

    def test_section_start_pages_precede_their_first_paragraph(self):
        from data.tarasenkova_toc_pages import PARAGRAPH_PAGES, SECTION_START_PAGES

        for section_number, section_page in SECTION_START_PAGES.items():
            first_paragraph = min(
                (p for p in PARAGRAPH_PAGES if p.section_number == section_number),
                key=lambda p: p.paragraph_number,
            )
            self.assertLess(section_page, first_paragraph.start_page)

    def test_covers_all_35_paragraphs_across_5_sections(self):
        from data.tarasenkova_toc_pages import PARAGRAPH_PAGES, SECTION_START_PAGES

        self.assertEqual(len(PARAGRAPH_PAGES), 35)
        self.assertEqual(set(SECTION_START_PAGES.keys()), {1, 2, 3, 4, 5})
        self.assertEqual(
            [p.paragraph_number for p in PARAGRAPH_PAGES], list(range(1, 36))
        )

    def test_get_paragraph_page_looks_up_by_number(self):
        from data.tarasenkova_toc_pages import get_paragraph_page

        p18 = get_paragraph_page(18)
        self.assertEqual(p18.title, "Циліндр. Конус. Куля")
        self.assertEqual(p18.start_page, 130)

        with self.assertRaises(KeyError):
            get_paragraph_page(999)
