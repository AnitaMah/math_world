"""Фаза 14Б: корпус регресій OCR.

Кожен тест — реальна помилка OCR (або баг старого парсера), яку ми бачили у PDF.
Назва тесту містить номер кроку плану (0603…0642), щоб легко знайти, звідки кейс.
Якщо тест упав — це не «застарілий тест», а повернення старої помилки.
"""
import unittest

import cv2
import numpy as np

from education.pdf_pipeline.answers import parse_answer_lines, split_parts
from education.pdf_pipeline.datatypes import BBox, Line, Node, PageImage, Word
from education.pdf_pipeline.exercises import figure_refs, split_exercise
from education.pdf_pipeline.grids import read_grid
from education.pdf_pipeline.layout import PageLayout, infer_book_pages, split_running_header
from education.pdf_pipeline.math_text import analyze_expression, detect_fraction_bars, enrich_math
from education.pdf_pipeline.normalize import join_hyphenation, normalize_lines
from education.pdf_pipeline.preprocess import PRESET_LOWRES, choose_preset
from education.pdf_pipeline.profiles import get_profile
from education.pdf_pipeline.profiles.base import TocEntry
from education.pdf_pipeline.structure import parse_structure
from education.pdf_pipeline.validate import check_pages_without_body, check_exercise_numbers

M5 = get_profile("math_merzlyak_5")
M5_TOC = [
    TocEntry("section", "I", "Натуральні числа і дії з ними"),
    TocEntry("paragraph", "1", "Натуральні числа"),
    TocEntry("item", "1", "Ряд натуральних чисел"),
    TocEntry("item", "2", "Цифри. Десятковий запис натуральних чисел"),
]


# --------------------------------------------------------------------------- помічники


def words_line(text, y=0, x=80, step=40, page=7, line_id=0, conf=90.0):
    words = [Word(t, BBox(x + i * step, y, x + i * step + step - 5, y + 18), conf) for i, t in enumerate(text.split())]
    return Line(words=words, page_index=page, line_id=line_id)


def cells_line(*cells, y=0):
    """Рядок сітки: (x, текст) для кожної клітинки."""
    words = []
    for x, text in cells:
        words += [Word(t, BBox(x + i * 30, y, x + i * 30 + 25, y + 18), 90.0) for i, t in enumerate(text.split())]
    return Line(words=words, page_index=7)


def norm(text):
    lines, _ = normalize_lines([words_line(text)])
    return lines[0].text if lines else ""


def norm_flags(text):
    lines, _ = normalize_lines([words_line(text)])
    return [f for w in lines[0].words for f in w.flags]


def page(pdf_page, *rows):
    """Сторінка для структурного парсера: рядок або (текст, висота шрифту)."""
    lines = []
    for i, row in enumerate(rows):
        text, h = (row, 14) if isinstance(row, str) else row
        y = 150 + i * 25
        ws = [Word(t, BBox(80 + j * 40, y, 80 + j * 40 + 35, y + h), 90.0) for j, t in enumerate(text.split())]
        lines.append(Line(words=ws, page_index=pdf_page, line_id=i))
    return PageLayout(pdf_page=pdf_page, page_height=1329, body_lines=lines, book_page=pdf_page)


LESSON_START = (("9 1. НАТУРАЛЬНІ ЧИСЛА", 20), ("1. РЯД натуральних чисел", 16.5), "Текст.")


def parse_m5(*pages):
    return parse_structure(M5, list(pages), toc=M5_TOC)


def exercises(result):
    return [n for n in result.root.walk() if n.kind == "exercise"]


def blocks(result):
    return [n.data["block_type"] for n in result.root.walk() if n.kind == "block"]


# --------------------------------------------------------------------------- нормалізація


class NormalizationRegressions(unittest.TestCase):
    def test_0603_bech_vses(self):
        self.assertEqual(norm("Записати Bech натуральний ряд"), "Записати весь натуральний ряд")

    def test_0604_b_ryadu(self):
        self.assertEqual(norm("Чи кожне число B ряду"), "Чи кожне число в ряду")

    def test_0605_ha(self):
        self.assertEqual(norm("числа. Ha уроці"), "числа. На уроці")
        self.assertEqual(norm("прийшли Ha урок"), "прийшли на урок")

    def test_0606_cboei_all_latin(self):
        self.assertEqual(norm("до cBoei мами"), "до своєї мами")

    def test_0624_typographic_apostrophe(self):
        self.assertEqual(norm("Розв’язуємо усно"), "Розв'язуємо усно")

    def test_0641_geometry_latin_kept(self):
        self.assertEqual(norm("відрізок AB дорівнює"), "відрізок AB дорівнює")

    def test_0642_equation_kept(self):
        self.assertEqual(norm("x + 5 = 12"), "x + 5 = 12")


class HyphenationRegressions(unittest.TestCase):
    def join(self, a, b):
        lines = [words_line(a, 0), words_line(b, 25)]
        join_hyphenation(lines)
        return [ln.text for ln in lines]

    def test_0615_naturalnyh(self):
        self.assertEqual(self.join("три наступних натураль-", "них числа.")[0], "три наступних натуральних")

    def test_0616_pereyaslavskoi(self):
        self.assertEqual(self.join("за Переяслав-", "ської, Київської")[0], "за Переяславської,")

    def test_0617_bud_yakyi_keeps_hyphen(self):
        self.assertEqual(self.join("візьми будь-", "який предмет")[0], "візьми будь-який")


class OperatorRegressions(unittest.TestCase):
    def test_0611_double_hyphen_in_expression(self):
        result = analyze_expression("43--24-")
        self.assertNotEqual(result.status, "ok")

    def test_0612_hyphen_is_suspect_operator(self):
        self.assertIn("suspect_operator", norm_flags("238 - 435"))
        self.assertEqual(analyze_expression("238- 435").status, "suspect")


# --------------------------------------------------------------------------- номери вправ і складність


class ExerciseStartRegressions(unittest.TestCase):
    def test_0607_quote_is_difficulty_mark(self):
        self.assertEqual(M5.parse_exercise_start('11." Деяке число'), (11, "sufficient", "Деяке число"))

    def test_0608_quote_after_dot_number_2(self):
        self.assertEqual(M5.parse_exercise_start('2." Скільки чисел'), (2, "sufficient", "Скільки чисел"))

    def test_0618_82_instead_of_32(self):
        r = parse_m5(page(5, *LESSON_START, ("Вправи", 23), *[f"{n}. Текст" for n in range(1, 32)], '82." Двоцифрове'))
        self.assertEqual(exercises(r)[-1].number, "32")
        self.assertTrue(exercises(r)[-1].data["number_fixed"])

    def test_0619_duplicate_number_both_kept(self):
        root = Node("textbook")
        block = root.add(Node("block", data={"block_type": "exercise"}))
        for n in ("5", "6", "6", "7"):
            block.add(Node("exercise", number=n, text="т"))
        self.assertEqual(len(root.find("exercise")), 4)                    # жодну не викинули
        self.assertEqual([p.code for p in check_exercise_numbers(root)], ["duplicate_exercise_number"])


# --------------------------------------------------------------------------- сітки і підпункти


class GridRegressions(unittest.TestCase):
    def test_0609_17_in_grid_is_7(self):
        lines = [cells_line((104, "1) 238 + 435;"), (317, "4) 2000 − 546;"), (529, "17) 98-34;"), y=0),
                 cells_line((103, "2) 4385 + 2697;"), (317, "5) 3400 − 896;"), (528, "8) 645 · 36."), y=25),
                 cells_line((103, "3) 843 − 457;"), (317, "6) 23 · 46;"), y=50)]
        grid = read_grid(lines, [0, 1, 2])
        self.assertEqual([c.label for c in grid.cells], ["1", "2", "3", "4", "5", "6", "7", "8"])
        self.assertTrue(next(c for c in grid.cells if c.label == "7").ocr_fixed)

    def test_0610_glued_marker(self):
        grid = read_grid([cells_line((104, "1)6 124;"), (317, "2)7 300;"), y=0)], [0])
        self.assertEqual([(c.label, c.text) for c in grid.cells], [("1", "6 124;"), ("2", "7 300;")])

    def test_0625_b_instead_of_6(self):
        lines = [cells_line((100, "4) a;"), y=0), cells_line((100, "5) b;"), y=25), cells_line((100, "б) c;"), y=50)]
        self.assertEqual([c.label for c in read_grid(lines, [0, 1, 2]).cells], ["4", "5", "6"])

    def test_0614_figure_ref_at_line_end(self):
        self.assertEqual(figure_refs("Знайдіть довжину відрізка AB (рис. 1)"), ["1"])
        self.assertEqual(figure_refs("зображені на рисунку 15."), ["15"])


# --------------------------------------------------------------------------- колонтитули і сторінки


class PageRegressions(unittest.TestCase):
    def test_0620_page_number_at_end_of_header(self):
        self.assertEqual(split_running_header(words_line("2. Цифри. Десятковий запис 7", 110)),
                         ("2. Цифри. Десятковий запис", 7))

    def test_0621_paragraph_header(self):
        self.assertEqual(split_running_header(words_line("6 51. Натуральні числа", 110)),
                         ("§ 1. Натуральні числа", 6))

    def test_0626_three_eight_in_page_number(self):
        pages = infer_book_pages({10: 10, 11: 11, 12: 12, 13: 18, 14: 14, 15: 15})
        self.assertEqual(pages[13], 13)

    def test_0635_low_res_preset(self):
        img = PageImage(pdf_page=92, path=None, width=640, height=900, dpi=76, low_res=True)
        self.assertIs(choose_preset(img), PRESET_LOWRES)

    def test_0636_empty_page(self):
        lay = PageLayout(pdf_page=2, page_height=1329, body_lines=[])
        self.assertEqual([p.code for p in check_pages_without_body([lay])], ["page_without_body"])


# --------------------------------------------------------------------------- маркери блоків і структура


class StructureRegressions(unittest.TestCase):
    def test_0613_owl_marker_with_icon_garbage(self):
        found = M5.match_block_marker("зб Задача від Мудрої Сови ох |")
        self.assertEqual(found[0].block_type if found else None, "wise_owl")

    def test_0622_owl_does_not_swallow_next_item(self):
        r = parse_m5(page(5, *LESSON_START, ("Вправи", 23), "1. А",
                          ("Задача від Мудрої Сови", 20), "Як розставити числа?",
                          ("2. ЦИФРИ. Десятковий запис натуральних чисел", 16.5), "Теорія пункту 2."))
        items = [n for n in r.root.walk() if n.kind == "item"]
        self.assertEqual([i.number for i in items], ["1", "2"])
        owl = next(n for n in r.root.walk() if n.kind == "block" and n.data["block_type"] == "wise_owl")
        self.assertNotIn("Теорія пункту 2", owl.text)

    def test_0623_history_ends_at_next_exercise_block(self):
        r = parse_m5(page(5, *LESSON_START, ("Вправи", 23), "1. А",
                          ("Коли зроблено уроки", 20), "Давні люди рахували на пальцях.",
                          ("2. ЦИФРИ. Десятковий запис натуральних чисел", 16.5), "Т.",
                          ("Вправи", 23), "2. Б"))
        self.assertEqual([e.number for e in exercises(r)], ["1", "2"])
        self.assertIn("history_aside", blocks(r))

    def test_0637_exercise_across_pages(self):
        r = parse_m5(page(5, *LESSON_START, ("Вправи", 23), "1. Почато на одній", "сторінці"),
                     page(6, "і закінчено на іншій.", "2. Наступна"))
        ex1 = exercises(r)[0]
        self.assertIn("закінчено", ex1.text)
        self.assertEqual({tuple(k)[0] for k in ex1.data["line_keys"]}, {5, 6})

    def test_0638_two_line_item_heading(self):
        r = parse_m5(page(5, *LESSON_START, ("Вправи", 23), "1. А",
                          ("2. ЦИФРИ. Десятковий запис", 16.5), ("натуральних чисел", 16.5), "Т."))
        items = [n for n in r.root.walk() if n.kind == "item"]
        self.assertEqual([i.number for i in items], ["1", "2"])

    def test_0639_word_vpravy_inside_sentence(self):
        self.assertIsNone(M5.match_block_marker("Ці вправи допоможуть"))

    def test_0640_review_exercises_not_plain(self):
        self.assertEqual(M5.match_block_marker("Вправи для повторення")[0].block_type, "review_exercise")


# --------------------------------------------------------------------------- відповіді


class AnswerRegressions(unittest.TestCase):
    def test_0627_colon_instead_of_semicolon(self):
        self.assertEqual(split_parts("1) 12: 16; 3) 30"), {"1": "12; 16", "3": "30"})

    def test_0628_no_spaces(self):
        key = parse_answer_lines([(296, "§ 27"), (296, "1183. 1) 4. 1184.1)5:2)0. 1185. 7")])
        self.assertEqual(key.get(1184).parts, {"1": "5", "2": "0"})

    def test_0629_negative_with_space(self):
        self.assertEqual(split_parts("1) - 76; 2) 4"), {"1": "-76", "2": "4"})

    def test_0630_decimal_does_not_split_subitems(self):
        self.assertEqual(split_parts("1) 3,5; 2) 80,09"), {"1": "3,5", "2": "80,09"})

    def test_0631_yes_no(self):
        self.assertEqual(split_parts("1) Hi; 2) Tak"), {"1": "ні", "2": "так"})

    def test_0632_sentence_answer(self):
        self.assertEqual(split_parts("Збільшилась на 5 учнів."), {"": "Збільшилась на 5 учнів"})


# --------------------------------------------------------------------------- дроби


def draw_fraction(img, x, y, whole=None):
    if whole:
        cv2.putText(img, whole, (x - 30, y + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1)
    cv2.putText(img, "1", (x - 4, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1)
    cv2.line(img, (x - 8, y), (x + 8, y), 0, 1)
    cv2.putText(img, "6", (x - 4, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1)


class FractionRegressions(unittest.TestCase):
    def fraction_exercise(self, whole):
        img = np.full((600, 400), 255, np.uint8)
        draw_fraction(img, 200, 300, whole)
        bars = detect_fraction_bars(img, text_height=18)
        root = Node("textbook")
        from education.pdf_pipeline.datatypes import SourceRef
        ex = root.add(Node("exercise", number="33", source=SourceRef(9, bbox=BBox(100, 250, 380, 350))))
        enrich_math(root, fraction_bars={9: bars})
        return ex

    def test_0633_two_storey_fraction(self):
        ex = self.fraction_exercise(None)
        self.assertTrue(ex.data.get("has_fractions"))
        self.assertTrue(ex.needs_review)

    def test_0634_mixed_number(self):
        self.assertTrue(self.fraction_exercise("2").data.get("has_fractions"))


if __name__ == "__main__":
    unittest.main()
