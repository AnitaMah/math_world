"""Тести структурного парсера на «міні-підручниках» з реальних рядків Мерзляка і Тарасенкової."""
import unittest

from education.pdf_pipeline.datatypes import BBox, Line, Word
from education.pdf_pipeline.layout import PageLayout
from education.pdf_pipeline.profiles import get_profile
from education.pdf_pipeline.profiles.base import TocEntry
from education.pdf_pipeline.structure import StructureParser, letter_number_candidates, number_fixable, outline, parse_structure

M5 = get_profile("math_merzlyak_5")
T6 = get_profile("math_tarasenkova_6")

M5_TOC = [
    TocEntry("section", "I", "Натуральні числа і дії з ними"),
    TocEntry("paragraph", "1", "Натуральні числа"),
    TocEntry("item", "1", "Ряд натуральних чисел"),
    TocEntry("item", "2", "Цифри. Десятковий запис натуральних чисел"),
]
T6_TOC = [
    TocEntry("section", "1", "Подільність натуральних чисел"),
    TocEntry("paragraph", "1", "Дільники і кратні натурального числа"),
    TocEntry("paragraph", "2", "Ознаки подільності на 2, 10, 5"),
]


def page(pdf_page: int, *rows) -> PageLayout:
    """rows: рядок тексту або (текст, висота). Висота за замовчуванням 14 px, як у Мерзляка."""
    lines = []
    for i, row in enumerate(rows):
        text, h = (row, 14) if isinstance(row, str) else row
        y = 150 + i * 25
        words = [Word(t, BBox(80 + j * 40, y, 80 + j * 40 + 35, y + h), 90.0) for j, t in enumerate(text.split())]
        lines.append(Line(words=words, page_index=pdf_page, line_id=i))
    return PageLayout(pdf_page=pdf_page, page_height=1329, body_lines=lines, book_page=pdf_page)


def kinds(node, kind):
    return [n for n in node.walk() if n.kind == kind]


def block_types(lesson):
    return [b.data["block_type"] for b in lesson.children if b.kind == "block"]


class NumberFixableTests(unittest.TestCase):
    def test_cases(self):
        self.assertTrue(number_fixable("88", 83))     # 3 ↔ 8
        self.assertTrue(number_fixable("168", 163))
        self.assertTrue(number_fixable("382", 32))    # зайва цифра (значок •)
        self.assertTrue(number_fixable("82", 8))      # «8.•» → «82»
        self.assertTrue(number_fixable("178", 78))
        self.assertFalse(number_fixable("45", 12))
        self.assertFalse(number_fixable("2", 12))


class LetterNumberTests(unittest.TestCase):
    def test_candidates(self):
        self.assertEqual(letter_number_candidates("о"), {0, 5})
        self.assertEqual(letter_number_candidates("1о"), {10, 15})
        self.assertEqual(letter_number_candidates("З"), {3})
        self.assertEqual(letter_number_candidates("ж"), set())


class MerzlyakMiniBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        layouts = [
            page(5,
                 ("9 1. НАТУРАЛЬНІ ЧИСЛА", 20),            # «§» прочитано як «9»
                 ("1. РЯД натуральних чисел", 16.5),
                 "Скільки днів залишилося до кінця канікул?",
                 "Числа 1, 2, 3, які використовують при лічбі, називають натуральними.",
                 ("оо. UA", 134),                          # сміття від картинки
                 "1. Як називають числа, що використовують при лічбі предметів?",
                 "2. Чи є серед натуральних чисел найменше число?",
                 ("Розв'язуємо усно", 21),
                 "1. Додайте:",
                 "1) 48 і 17; 2) 16 і 19;",
                 "2. Відніміть:"),
            page(6,
                 ("Вправи", 23),
                 "1. Назвіть 14 перших натуральних чисел.",
                 "2. Якого числа не вистачає в записі,",
                 "щоб він позначав натуральний ряд?",
                 '3." Деяке натуральне число позначили буквою a.',
                 "Puc. 1",
                 ("Вправи для повторення", 19),
                 "4. Обчисліть:",
                 ("Задача від Мудрої Сови", 21),
                 "5. У квадраті суми чисел мають бути рівними.",
                 ("2. Цифри. Десятковий запис натуральних чисел", 16.5),
                 "Як дім будують із цеглин, так числа записують цифрами.",
                 ("Розв'язуємо усно", 21),
                 "1. Наскільки:",
                 ("Вправи", 23),
                 "6. Назвіть розряд.",
                 ("Коли зроблено уроки", 19),
                 "Ще в кам'яному віці люди вміли рахувати."),
            page(7,
                 "Завдання № 1 «Перевірте себе» в тестовій формі",
                 "1. Укажіть правильну нерівність:"),
        ]
        cls.result = parse_structure(M5, layouts, toc=M5_TOC)
        cls.root = cls.result.root

    def test_hierarchy(self):
        sections = kinds(self.root, "section")
        self.assertEqual([(s.number, s.title) for s in sections], [("I", "Натуральні числа і дії з ними")])
        self.assertEqual([p.number for p in kinds(self.root, "paragraph")], ["1"])
        items = kinds(self.root, "item")
        self.assertEqual([(i.number, i.title) for i in items],
                         [("1", "Ряд натуральних чисел"), ("2", "Цифри. Десятковий запис натуральних чисел")])

    def test_blocks_of_first_item(self):
        item1 = kinds(self.root, "item")[0]
        self.assertEqual(block_types(item1),
                         ["theory", "self_check", "oral_exercise", "exercise", "review_exercise", "wise_owl"])
        theory = item1.children[0]
        self.assertIn("називають натуральними", theory.text)
        self.assertNotIn("UA", theory.text)                    # сміття відкинуто
        self.assertIn("2. Чи є серед", item1.children[1].text)

    def test_oral_numbering_restarts_and_exercises_are_global(self):
        item1 = kinds(self.root, "item")[0]
        oral = item1.children[2]
        self.assertEqual([e.number for e in oral.children], ["1", "2"])
        self.assertIn("1) 48 і 17", oral.children[0].text)     # продовження вправи дописується до неї
        exercises = item1.children[3]
        self.assertEqual([e.number for e in exercises.children], ["1", "2", "3"])
        self.assertEqual(exercises.children[1].text, "Якого числа не вистачає в записі,\nщоб він позначав натуральний ряд?")
        self.assertEqual(exercises.children[2].data["difficulty"], "sufficient")
        self.assertNotIn("Puc", exercises.children[2].text)     # підпис рисунка не в тексті

    def test_review_and_owl_continue_numbering(self):
        item1 = kinds(self.root, "item")[0]
        self.assertEqual(item1.children[4].children[0].number, "4")
        self.assertEqual(item1.children[5].children[0].number, "5")

    def test_second_item_and_history(self):
        item2 = kinds(self.root, "item")[1]
        self.assertEqual(block_types(item2), ["theory", "oral_exercise", "exercise", "history_aside"])
        self.assertEqual(item2.children[2].children[0].number, "6")
        self.assertIn("кам'яному віці", item2.children[3].text)

    def test_self_test_belongs_to_paragraph(self):
        paragraph = kinds(self.root, "paragraph")[0]
        self.assertEqual(paragraph.children[-1].data["block_type"], "self_test")

    def test_source_refs(self):
        item2 = kinds(self.root, "item")[1]
        self.assertEqual(item2.source.pdf_page, 6)
        ex = kinds(self.root, "exercise")[3]
        self.assertEqual(ex.data["line_keys"][0][0], 6)

    def test_noise_counted(self):
        self.assertGreaterEqual(self.result.skipped_noise, 2)

    def test_outline_renders(self):
        text = outline(self.root)
        self.assertIn("item 2 «Цифри", text)
        self.assertIn("wise_owl", text)


class ExerciseNumberingTests(unittest.TestCase):
    def parse(self, *rows):
        layouts = [page(5, ("9 1. НАТУРАЛЬНІ ЧИСЛА", 20), ("1. РЯД натуральних чисел", 16.5), "Текст.",
                        ("Вправи", 23), *rows)]
        return parse_structure(M5, layouts, toc=M5_TOC)

    def numbers(self, result):
        return [e.number for e in kinds(result.root, "exercise")]

    def test_three_eight_confusion(self):
        r = self.parse("1. А", "2. Б", "8. В", "4. Г")
        self.assertEqual(self.numbers(r), ["1", "2", "3", "4"])
        self.assertEqual([i.code for i in r.issues if i.code.startswith("exercise")], ["exercise_number_fixed"])

    def test_missing_dot_and_comma(self):
        r = self.parse("1. А", "2 Скільки", "3, Назвіть")
        self.assertEqual(self.numbers(r), ["1", "2", "3"])

    def test_gap_is_reported(self):
        r = self.parse("1. А", "2. Б", "4. Г")
        self.assertEqual(self.numbers(r), ["1", "2", "4"])
        self.assertIn("exercise_number_gap", [i.code for i in r.issues])

    def test_far_number_is_text(self):
        r = self.parse("1. А", "250. Б")
        self.assertEqual(self.numbers(r), ["1"])
        self.assertIn("250. Б", kinds(r.root, "exercise")[0].text)

    def test_grid_line_is_not_exercise(self):
        r = self.parse("1. Обчисліть:", "1) 238 + 435; 2) 4385 + 2697;")
        self.assertEqual(self.numbers(r), ["1"])


class TarasenkovaMiniBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        layouts = [
            page(5,
                 ("§ 1. ДІЛЬНИКИ І КРАТНІ НАТУРАЛЬНОГО ЧИСЛА", 20),
                 "Подивіться на малюнок 1. Ви бачите, що 6 яблук поділили на 2 купки.",
                 ("Запам'ятайте!", 15),
                 "Дільником числа називається таке число, на яке ділиться дане число.",
                 "З а д а ч а . Знайдіть усі дільники числа: 1) 7; 2) 12.",
                 "Розв'язання. 1) У числа 7 є два дільники.",
                 ("ПРИГАДАЙТЕ ГОЛОВНЕ", 16),
                 "1. Що таке дільник числа?",
                 ("РОЗВ'ЯЖІТЬ ЗАДАЧІ", 16),
                 "1′. Назвіть дільники числа 6.",
                 "2°. Чи є число 3 дільником 12?",
                 "3. Знайдіть усі дільники числа 24.",
                 "4*. Доведіть, що число 1 має один дільник."),
            page(9,
                 ("ЗАДАЧІ НА ПОВТОРЕННЯ", 16),
                 "5. Обчисліть: 1) 2 + 3; 2) 5 + 6.",
                 ("§ 2. ОЗНАКИ ПОДІЛЬНОСТІ НА 2, 10, 5", 20),
                 "Запишемо натуральний ряд чисел:",
                 ("РОЗВ'ЯЖІТЬ ЗАДАЧІ", 16),
                 "6′. Назвіть три парні числа."),
        ]
        cls.root = parse_structure(T6, layouts, toc=T6_TOC).root

    def test_paragraphs_are_lessons(self):
        self.assertEqual(kinds(self.root, "item"), [])
        self.assertEqual([p.number for p in kinds(self.root, "paragraph")], ["1", "2"])

    def test_blocks(self):
        p1 = kinds(self.root, "paragraph")[0]
        self.assertEqual(block_types(p1), ["theory", "rule", "worked_example", "self_check", "exercise", "review_exercise"])
        self.assertIn("Розв'язання", p1.children[2].text)

    def test_difficulty(self):
        ex = kinds(kinds(self.root, "paragraph")[0], "exercise")
        self.assertEqual([(e.number, e.data["difficulty"]) for e in ex],
                         [("1", "preparatory"), ("2", "medium"), ("3", "sufficient"), ("4", "high"), ("5", "sufficient")])

    def test_global_numbering_continues(self):
        p2 = kinds(self.root, "paragraph")[1]
        self.assertEqual([e.number for e in kinds(p2, "exercise")], ["6"])


class InvariantTests(unittest.TestCase):
    def test_lesson_without_exercises(self):
        layouts = [page(5, ("9 1. НАТУРАЛЬНІ ЧИСЛА", 20), ("1. РЯД натуральних чисел", 16.5), "Лише теорія.")]
        r = parse_structure(M5, layouts, toc=M5_TOC)
        self.assertIn("lesson_without_exercises", [i.code for i in r.issues])


if __name__ == "__main__":
    unittest.main()


class ParagraphHeadingInHeaderBandTests(unittest.TestCase):
    """§ 5 стоїть так високо (y≈56pt), що рядок потрапляє в колонтитул без номера сторінки."""

    @staticmethod
    def _header_page(pdf_page, heading, *rows):
        lay = page(pdf_page, *rows)
        words = [Word(t, BBox(80 + j * 60, 40, 80 + j * 60 + 50, 70), 99.0) for j, t in enumerate(heading.split())]
        lay.header_lines = [Line(words=words, page_index=pdf_page, line_id=99, zone="header")]
        return lay

    def test_heading_opens_paragraph_once(self):
        toc = [TocEntry("section", "I", "Натуральні числа і дії з ними"),
               TocEntry("paragraph", "1", "Натуральні числа"),
               TocEntry("item", "1", "Ряд натуральних чисел")]
        layouts = [self._header_page(5, "§ 1. Натуральні числа", "1. Ряд натуральних чисел", "Текст пункту."),
                   self._header_page(6, "§ 1. Натуральні числа", "Ще текст.")]
        root = parse_structure(M5, layouts, toc=toc).root
        self.assertEqual([p.number for p in kinds(root, "paragraph")], ["1"])


class FirstExerciseTests(unittest.TestCase):
    """Прогін частини книги: нумерація вправ починається не з 1 (пробні стор. 20–30 Тарасенкової: №188...)."""

    PAGES = [
        page(26, ("§ 1. ДІЛЬНИКИ І КРАТНІ НАТУРАЛЬНОГО ЧИСЛА", 20), "Теорія."),
        page(29, "Застосуйте на практиці",
             "188. Уздовж дороги від міста стояли стовпи.", "189. Довжина відрізка дорівнює 24 см.",
             "190°. Знайдіть три числа."),
    ]

    def numbers(self, **kw):
        res = parse_structure(T6, self.PAGES, T6_TOC, **kw)
        return [int(e.number) for e in kinds(res.root, "exercise")]

    def test_default_start_finds_nothing_mid_book(self):
        self.assertEqual(self.numbers(), [])               # очікувано 1, знайшли 188 — не вправи

    def test_first_exercise_makes_them_exercises(self):
        self.assertEqual(self.numbers(first_exercise=188), [188, 189, 190])


class NoisyTarasenkovaTests(unittest.TestCase):
    """Реальні рядки OCR стор. 28–29 Тарасенкової: заголовок із сміттям і зіпсовані номери."""

    PAGES = [
        page(26, ("§ 1. ДІЛЬНИКИ І КРАТНІ НАТУРАЛЬНОГО ЧИСЛА", 20), "Теорія."),
        page(27, "ПРИГАДАЙТЕ ГОЛОВНЕ", "Що таке дільник числа?"),
        page(28, "stash У РОЗВ'ЯЖІТЬ ЗАДАЧІ |",
             "11337762\". Назвіть числа.", "163\". Знайдіть дільники.", "1657. Запишіть числа.",
             "766\". Обчисліть значення.", "167°. Порівняйте числа.", "є 768\". Знайдіть суму.",
             "169°. Знайдіть різницю.", "1707. Запишіть добуток.", "7717. Розкладіть число.",
             "1727. Знайдіть частку."),
        page(29, "А 174°. Обчисліть вираз.", "а. 780. Знайдіть НСК.", "Ж 182. Знайдіть НСД."),
    ]

    def numbers(self):
        res = parse_structure(T6, self.PAGES, T6_TOC, first_exercise=162)
        return [int(e.number) for e in kinds(res.root, "exercise")]

    def test_noisy_heading_opens_exercise_block(self):
        nums = self.numbers()
        self.assertTrue(nums, "заголовок із сміттям має відкрити блок вправ")
        self.assertIn(163, nums)

    def test_garbled_numbers_are_repaired(self):
        nums = self.numbers()
        for n in (165, 166, 168, 170, 171, 172, 174):
            self.assertIn(n, nums)

    def test_number_fixable_icon_read_as_digit(self):
        self.assertTrue(number_fixable("1657", 165))
        self.assertTrue(number_fixable("7717", 171))
        self.assertTrue(number_fixable("766", 166))
        self.assertFalse(number_fixable("1957", 165))


class BookPageOffsetTests(unittest.TestCase):
    def test_tarasenkova_book_page_equals_pdf_page(self):
        self.assertEqual(T6.book_page_offset, 0)

    def test_merzlyak_has_no_offset(self):
        self.assertIsNone(get_profile("math_merzlyak_5").book_page_offset)
