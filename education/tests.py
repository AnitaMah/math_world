from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from education.models import Grade, Item, Paragraph, Section, Subject
from education.parsing.content_classifier import (
    find_exercise_blocks,
    find_history_aside_blocks,
    find_oral_exercise_blocks,
    find_review_exercise_blocks,
    find_wise_owl_blocks,
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


class ImportCurriculumDryRunTests(TestCase):
    """
    Step 20: import_curriculum --dry-run wires the same management
    command to the Step 15-19 content classifiers (via
    collect_content_block_previews) instead of the TOC importer above --
    given raw OCR'd lesson text, it prints the ContentBlocks that would
    be created without touching the database at all.
    """

    def setUp(self):
        self.content_file = Path(settings.BASE_DIR) / "review" / "section_1_text" / "combined.txt"

    def test_dry_run_requires_content_file(self):
        with self.assertRaises(CommandError):
            call_command("import_curriculum", "--dry-run", stdout=StringIO())

    def test_dry_run_prints_previews_without_writing_to_db(self):
        out = StringIO()
        call_command(
            "import_curriculum", "--dry-run", "--content-file", str(self.content_file), stdout=out
        )
        output = out.getvalue()
        self.assertIn("ContentBlock", output)
        self.assertIn("exercise", output)
        self.assertIn("history_aside", output)
        self.assertEqual(Grade.objects.count(), 0)
        self.assertEqual(Section.objects.count(), 0)
        self.assertEqual(Paragraph.objects.count(), 0)
        self.assertEqual(Item.objects.count(), 0)

    def test_dry_run_does_not_require_file_or_grade(self):
        out = StringIO()
        call_command(
            "import_curriculum", "--dry-run", "--content-file", str(self.content_file), stdout=out
        )
        self.assertIn("ContentBlock", out.getvalue())

    def test_dry_run_orders_previews_by_document_position(self):
        out = StringIO()
        call_command(
            "import_curriculum", "--dry-run", "--content-file", str(self.content_file), stdout=out
        )
        output = out.getvalue()
        self.assertLess(output.index("oral_exercise"), output.index(" exercise"))


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

    # Step 18: verbatim excerpts of both real "Задача від Мудрої Сови"
    # occurrences in review/section_1_text/combined.txt. The first (lines
    # 111-123) has the garbled "зб ... ох |" OCR prefix on the marker
    # line and, right after its single problem, bleeds straight into the
    # *next lesson's title* with no marker of its own -- the hardest real
    # case, since the block must end at the blank line rather than
    # swallowing that next lesson. The second (lines 344-354) is cleaner
    # OCR-wise ("з»" prefix) and ends at a proper "Коли зроблено уроки"
    # marker instead.
    WISE_OWL_EXCERPT_WITH_LESSON_BLEED = """\
16. На одній ділянці ростуть 34 кущі смородини, а на другій -- на
18 кущів менше. Скільки всього кущів смородини росте на двох
ділянках?

зб Задача від Мудрої Сови ох |

17. У квадраті (рис. 1) суми чисел, записаних у кож- ор зі
ному стовпчику, у кожному рядку і на кожній
діагоналі, яка містить три клітини, мають бути мі
рівними. Знайдіть число, яке має бути записане
замість зірочки. Рис. 1

2. Цифри. Десятковий запис натуральних чисел
"""

    WISE_OWL_EXCERPT_ENDING_AT_HISTORY_ASIDE = """\
43. За три дні коваль Вакула виготовив 432 підкови. Скільки підків
він виготовить за 5 днів, працюючи так само завзято?

з» Задача від Мудрої Сови

44. У цьому році день народження батька був у неділю. У який
день тижня святкувала день народження мати, якщо вона на
62 дні молодша від батька?

Коли зроблено уроки
Як рахували в давнину
"""

    def test_wise_owl_block_found_despite_garbled_marker_prefix(self):
        blocks = find_wise_owl_blocks(self.WISE_OWL_EXCERPT_WITH_LESSON_BLEED)
        self.assertEqual(len(blocks), 1)
        self.assertIn("17. У квадраті", blocks[0].text)

    def test_wise_owl_block_stops_before_next_lesson_bleed_through(self):
        blocks = find_wise_owl_blocks(self.WISE_OWL_EXCERPT_WITH_LESSON_BLEED)
        # The next lesson's title bleeds in right after the block, with
        # no marker of its own -- it must not leak into the captured text.
        self.assertNotIn("Цифри. Десятковий запис", blocks[0].text)

    def test_wise_owl_block_found_with_clean_marker(self):
        blocks = find_wise_owl_blocks(self.WISE_OWL_EXCERPT_ENDING_AT_HISTORY_ASIDE)
        self.assertEqual(len(blocks), 1)
        self.assertIn("44. У цьому році", blocks[0].text)

    def test_wise_owl_block_stops_before_history_aside_marker(self):
        blocks = find_wise_owl_blocks(self.WISE_OWL_EXCERPT_ENDING_AT_HISTORY_ASIDE)
        self.assertNotIn("Коли зроблено уроки", blocks[0].text)

    def test_no_marker_means_no_wise_owl_blocks(self):
        self.assertEqual(find_wise_owl_blocks("Просто якийсь текст."), [])

    # Step 19: verbatim excerpt of the one real "Коли зроблено уроки"
    # occurrence in review/section_1_text/combined.txt (lines 353-494,
    # the full historical aside plus the next lesson's heading it must
    # stop before). The plan itself calls this block type "hardest,
    # spans a page-layout box" -- unlike every other block tested above,
    # this is a genuine ~140-line multi-paragraph essay with an internal
    # sub-heading of its own ("Як називають «числа-велетні»") and
    # running-header bleed-through scattered through it
    # ("Як рахували в давнину 13", "їщ 9 1. Натуральні числа"), none of
    # which has any special handling -- it's tested here specifically to
    # confirm none of that noise causes the block to end early or spill
    # over into the next lesson.
    HISTORY_ASIDE_EXCERPT = """\
Коли зроблено уроки
Як рахували в давнину
У місцях, де жили стародавні люди, археологи знаходять предме-
ти з вибитими крапками, надряпаними рисочками, глибокими заруб-
ками. Ці знахідки дозволяють припустити, що вже в кам'яному віці
люди вміли не лише рахувати, а й фіксувати
(«записувати») результати своїх підрахунків.
З розвитком суспільства вдосконалюва-
лися і способи лічби. Адже такі примітивні
Як рахували в давнину 13
засоби лічби, як зарубки на палиці, вузли на мотузці або камінці,
складені в купки, не могли задовольнити потреби торгівлі та ви-
робництва.

Приблизно за 3000 років до н. е. було зроблено найважливіше
відкриття: люди винайшли спеціальні знаки для позначення певної
кількості предметів. Наприклад, єгиптяни десяток позначали сим-
волом Й, сотню -- символом Є. Число 123 записували так: ЄПІПІЙІ.

У Стародавньому Римі записували числа за допомогою таких
цифр:

І -- один; С -- сто;

У -- п'ять;  -- п'ятсот;

Х -- десять; М-- тисяча.

І, -- п'ятдесят;

Римська система числення грунтується на такому принципі:
якщо при читанні зліва направо менша цифра стоїть після більшої,
то вона додається до більшої: УІ - 6, ХХ ХП - 32; якщо менша циф-
ра стоїть перед більшою, то вона віднімається від більшої: ГУ- 4,
МІ «45.

У римській системі числення, наприклад, число 14 записують
так: ХТУ. Тут цифра І стоїть між двома більшими цифрами Х 1 У.
У такому разі цифру І віднімають від цифри, яка стоїть праворуч
від неї (у нашому прикладі це цифра У).

Рік 1814-й, у якому народився Тарас Шевченко, за допомогою
римських цифр можна записати так: МОСССХТУ.

Ця система збереглася до наших днів. Часто можна зустріти
записи, де використано римські цифри, наприклад: ХХІ століття,
глава УЇ. Також їх можна побачити на циферблатах годинників,
пам'ятниках архітектури.

"ту
і т
Успенський собор (м. Харків)
їщ 9 1. Натуральні числа

Ви, мабуть, уже помітили, що навіть прочитати число, записа-
не римськими цифрами, нелегко. Тим більше складно виконувати
в такому записі чисел арифметичні дії з ними. Крім того, якщо по-
трібно записувати досить великі числа (мільйон, мільярд тощо), то
слід придумувати нові цифри. Інакше запис числа буде дуже довгим.
Наприклад, якщо для запису числа 1 000 000 використовувати
тільки римську цифру М, то запис буде складатися з тисячі таких
знаків. Усі ці недоліки істотно звужують можливість застосування
римської системи числення.

У Стародавній Русі не стали придумувати спеціальні знаки для
позначення цифр. Для цього використовували букви алфавіту. Над
буквою ставили хвилясту лінію -- титло. -г

Наприклад, число 241 записували так: ЄЙЛ А.

А В г а 6 5 3 и 5»
1 2 3 4 5 6 т 8 9

їТ Кк Аа но А 5 п я
10 20 30 40 | 50 | 60 то 80 90
- " "а та - - - -

р с т у ь хх ї кю ц
100 200 300 400 500 600 700 800 900

Одним з найвидатніших досягнень людства є винахід десят-
кової позиційної системи числення. За допомогою цієї системи
записують як завгодно великі числа, використовуючи лише десять
різних цифр. Таке можливо тому, що одна й та сама цифра має
різні значення залежно від її позиції в числі.

Цифри 0, 1,2,3,4, 5,6, 7, 8, 9 називають арабськими. Проте
араби лише розповсюдили десяткову позиційну систему, створену
індусами.

Деякі племена та народи використовували інші позиційні сис-
теми числення. Наприклад, індіанці племені майя використовували
двадцяткову систему, а стародавній народ шумери -- шістдесяткову.

Сліди двадцяткової системи можна віднайти в деяких євро-
пейських мовах. Так, французи замість «вісімдесят» говорять
«чотири рази по двадцять» (диаїге-ріпеїз). Розбиття однієї години
на 60 хвилин, а однієї хвилини на 60 секунд -- приклад явного
спадку шістдесяткової системи.

Лічба за допомогою десяти пальців рук спричинила появу десят-
кової системи. Загальна кількість пальців на руках і на ногах стала
основою для створення двадцяткової системи. «Пальцьове» походжен-
ня має і дванадцяткова система: спробуйте великим пальцем руки
Як називають «числа-велетні» 15
підрахувати фаланги на інших пальцях цієї ж руки, ї
вийде 12 (рис. 2). Так виникла лічба дюжинами. 7! ЩО

І за наших днів у Європі дюжинами продають 39 ї2є г
носовички, гудзики, курячі яйця. Кількість пред- 73. 2 р
метів у столових приборах і сервізах (виделки, ;
ножі, ложки, тарілки, чашки, бокали тощо), як хо
правило, дорівнює 6 (півдюжина), 12, 24 і т. д. , -'

Існують також інші позиційні системи числен- хе
ня. Так, побудова і робота комп'ютера грунтують- у
ся на двійковій системі числення, яка використо-
вує лише дві цифри -- 01 1. Більш докладно про Рис. 2
двійкову систему числення ви дізнаєтесь на уроках інформатики.

Як називають «числа-велетні»

Число мільйон -- велике чи мале? Наприклад, щоб провести
на уроках один мільйон хвилин, вам довелося б навчатися в школі
близько 20 років. Цей приклад показує, що мільйон -- велике число.

Однак для задоволення потреб таких наук, як економіка, астро-
номія, фізика, хімія, потрібні числа, що значно більші за мільйон.

Тисячу мільйонів називають більйоном або мільярдом, тисячу
більйонів -- трильйоном. Якщо до трильйона приписати праворуч
три нулі, то отримаємо квадрильйон. Далі, приписуючи кожного
разу по три нулі, отримаємо послідовність чисел, що мають такі на-
зви: квінтильйон, секстильйон, септильйон, октильйон, нонільйон.

Є назви й у чисел, більших від нонільйона (див. форзац).

Щоб ви могли уявити, наскільки величезні ці числа, наведемо
ще один приклад. Вік нашого Всесвіту, за оцінками вчених, не
перевищує квінтильйона хвилин.

3. Відрізок. Довжина відрізка
"""

    def test_history_aside_block_captures_the_full_essay(self):
        blocks = find_history_aside_blocks(self.HISTORY_ASIDE_EXCERPT)
        self.assertEqual(len(blocks), 1)
        self.assertIn("Як рахували в давнину", blocks[0].text)
        # The internal sub-heading is just more prose to this classifier
        # -- it must survive inside the one captured block, not get cut.
        self.assertIn("Як називають «числа-велетні»", blocks[0].text)

    def test_history_aside_block_unaffected_by_page_header_bleed(self):
        blocks = find_history_aside_blocks(self.HISTORY_ASIDE_EXCERPT)
        # These running-header bleed lines must survive as ordinary text
        # rather than prematurely ending the block.
        self.assertIn("Успенський собор", blocks[0].text)
        self.assertIn("квінтильйона хвилин", blocks[0].text)

    def test_history_aside_block_stops_before_next_lesson_heading(self):
        blocks = find_history_aside_blocks(self.HISTORY_ASIDE_EXCERPT)
        self.assertNotIn("Відрізок. Довжина відрізка", blocks[0].text)

    def test_no_marker_means_no_history_aside_blocks(self):
        self.assertEqual(find_history_aside_blocks("Просто якийсь текст."), [])


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
