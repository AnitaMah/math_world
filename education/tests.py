from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from education.models import Grade, Item, Paragraph, Section, Subject
from education.parsing.content_classifier import (
    find_exercise_blocks,
    find_oral_exercise_blocks,
    find_review_exercise_blocks,
)
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

    # Step 16: verbatim excerpt of item 1's plain "Вправи" list, real OCR
    # text -- including the genuine page-header bleed-through
    # ("2. Цифри. Десятковий запис натуральних чисел 7") that appears
    # mid-list and looks exactly like a new numbered exercise, and the
    # real difficulty markers OCR renders as a straight quote after
    # items 2 and 6.
    EXERCISE_EXCERPT = """\
Вправи
1. Назвіть 14 перших натуральних чисел.
2." Якого числа не вистачає в записі, щоб він позначав натуральний
ряд: 1,2, 3,4,5, 6, 7, 9, 10, 11,...?
3. Із чисел 5, 1 8, 129,0, з 4128, 5 виберіть натуральні.
6
4. Яке число в натуральному ряду стоїть за числом:
1) 34; 2) 246; 3) 8297?
5. Запишіть число, яке в натуральному ряду стоїть за числом:
1) 72; 2) 121; 3) 6459.
6." Яке число в натуральному ряду передує числу:
1) 58; 2) 631; 3) 4500?
7. Запишіть число, яке в натуральному ряду передує числу:
1) 42; 2) 215; 3) 3240.
2. Цифри. Десятковий запис натуральних чисел 7

8. Скільки чисел стоїть у натуральному ряду між числами:
1)6 124; 2) 18 181?
Вправи для повторення
"""

    def test_exercise_block_finds_all_items_in_order(self):
        blocks = find_exercise_blocks(self.EXERCISE_EXCERPT)
        self.assertEqual(len(blocks), 1)
        numbers = [item.number for item in blocks[0].items]
        self.assertEqual(numbers, [1, 2, 3, 4, 5, 6, 7, 8])

    def test_exercise_block_captures_difficulty_markers(self):
        blocks = find_exercise_blocks(self.EXERCISE_EXCERPT)
        by_number = {item.number: item for item in blocks[0].items}
        self.assertEqual(by_number[2].difficulty, "basic")
        self.assertEqual(by_number[6].difficulty, "basic")
        self.assertIsNone(by_number[1].difficulty)
        self.assertIsNone(by_number[7].difficulty)

    def test_exercise_block_absorbs_page_header_bleed_without_creating_bogus_item(self):
        blocks = find_exercise_blocks(self.EXERCISE_EXCERPT)
        numbers = [item.number for item in blocks[0].items]
        # The page-header bleed line re-uses "2." mid-list -- it must
        # NOT appear as a second, out-of-order item 2.
        self.assertEqual(numbers.count(2), 1)
        # Its text should have been folded into item 7 (the item open
        # when the bleed line appeared), not silently dropped.
        by_number = {item.number: item for item in blocks[0].items}
        self.assertIn("Цифри. Десятковий запис", by_number[7].text)

    def test_exercise_block_stops_before_review_exercise_marker(self):
        blocks = find_exercise_blocks(self.EXERCISE_EXCERPT)
        all_text = " ".join(item.text for item in blocks[0].items)
        self.assertNotIn("Вправи для повторення", all_text)

    # Step 17: verbatim excerpt of item 1's "Розв'язуємо усно" (mental-math
    # warm-up) block, real OCR text (review/section_1_text/combined.txt,
    # lines 44-57) -- a plain numbered list with no difficulty markers,
    # ending at the following bare "Вправи" heading.
    ORAL_EXERCISE_EXCERPT = """\
Розв'язуємо усно
1. Додайте:
1)4817; 2)1619; 3)25 134; 4) 52 149.
2. Відніміть:
1) 6 від 14; 2) 7 від 23; 3)відЗ32 число 3; 4)від 45 число 19.
3. Помножте:
1) 12 на 4; 2) 5 на 20; 3) 13 на 6; 4)10 на 100.
4. Поділіть:
1)36 на 12; 2)55 на11; 3)над8 число 96; 4)на 20 число 160.
5. Біля школи ростуть каштани і тополі. Каштанів росте 7, а то-
поль -- у З рази більше. Скільки дерев росте біля школи?
6. У школі 370 учнів. Чи знайдуться серед них хоча б два учні, які
святкують день народження в один і той самий день?
Вправи
"""

    def test_oral_exercise_block_finds_all_items_in_order(self):
        blocks = find_oral_exercise_blocks(self.ORAL_EXERCISE_EXCERPT)
        self.assertEqual(len(blocks), 1)
        numbers = [item.number for item in blocks[0].items]
        self.assertEqual(numbers, [1, 2, 3, 4, 5, 6])

    def test_oral_exercise_block_captures_multiline_item_text(self):
        blocks = find_oral_exercise_blocks(self.ORAL_EXERCISE_EXCERPT)
        by_number = {item.number: item for item in blocks[0].items}
        # Item 5's sentence wraps onto the next OCR line ("а то-" / "поль
        # -- у..."); the continuation must be folded into item 5's text,
        # not dropped or treated as a new item.
        self.assertIn("Каштанів росте 7", by_number[5].text)
        self.assertIn("поль -- у З рази більше", by_number[5].text)

    def test_oral_exercise_block_stops_before_exercise_marker(self):
        blocks = find_oral_exercise_blocks(self.ORAL_EXERCISE_EXCERPT)
        all_text = " ".join(item.text for item in blocks[0].items)
        self.assertNotIn("Вправи", all_text)

    def test_no_marker_means_no_oral_exercise_blocks(self):
        self.assertEqual(find_oral_exercise_blocks("Просто якийсь текст."), [])


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
