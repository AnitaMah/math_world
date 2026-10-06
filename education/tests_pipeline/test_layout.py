"""Тести для education.pdf_pipeline.layout: колонтитули і номери сторінок."""
import unittest
from pathlib import Path

from education.pdf_pipeline.datatypes import BBox, Line, PageImage, PageOcr, Word
from education.pdf_pipeline.layout import (
    PageLayout, analyze_document, analyze_page, collect_running_headers, fix_paragraph_sign,
    infer_book_pages, is_page_number, split_running_header,
)

PAGE_H = 1329   # висота сторінки Мерзляка в пікселях


def line(text: str, y: int, x: int = 130, line_no: int = 1) -> Line:
    """Рядок зі слів через пробіл на висоті y (кожне слово 40 px завширшки)."""
    words = [Word(t, BBox(x + i * 50, y, x + i * 50 + 40, y + 20), 90.0, 1, 1, line_no)
             for i, t in enumerate(text.split())]
    return Line(words=words, page_index=1)


class PageNumberTests(unittest.TestCase):
    def test_is_page_number(self):
        for ok in ["7", "46", "305"]:
            self.assertTrue(is_page_number(ok), ok)
        for bad in ["7.", "12)", "0", "1000", "a7", ""]:
            self.assertFalse(is_page_number(bad), bad)

    def test_fix_paragraph_sign(self):
        self.assertEqual(fix_paragraph_sign("51. Натуральні числа"), "§ 1. Натуральні числа")
        self.assertEqual(fix_paragraph_sign("S2. Додавання"), "§ 2. Додавання")
        self.assertEqual(fix_paragraph_sign("2. Цифри"), "2. Цифри")      # звичайний пункт не чіпаємо

    def test_split_number_at_end(self):
        title, num = split_running_header(line("2. Цифри. Десятковий запис 7", 110))
        self.assertEqual((title, num), ("2. Цифри. Десятковий запис", 7))

    def test_split_number_at_start(self):
        self.assertEqual(split_running_header(line("6 51. Натуральні числа", 110)),
                         ("§ 1. Натуральні числа", 6))

    def test_split_without_number(self):
        self.assertEqual(split_running_header(line("ПОДІЛЬНІСТЬ ЧИСЕЛ", 110)), ("ПОДІЛЬНІСТЬ ЧИСЕЛ", None))

    def test_only_number(self):
        self.assertEqual(split_running_header(line("11", 110)), ("", 11))


class AnalyzePageTests(unittest.TestCase):
    def test_header_removed_from_body(self):
        lines = [
            line("2. Цифри. Десятковий запис натуральних чисел 7", 110),
            line("8. Скільки чисел стоїть", 165),
            line("2. Цифри. Десятковий запис натуральних чисел", 900),   # справжній заголовок пункту!
        ]
        lay = analyze_page(lines, pdf_page=7, page_height=PAGE_H)
        self.assertEqual(lay.header_title, "2. Цифри. Десятковий запис натуральних чисел")
        self.assertEqual(lay.detected_book_page, 7)
        self.assertEqual([ln.text for ln in lay.body_lines],
                         ["8. Скільки чисел стоїть", "2. Цифри. Десятковий запис натуральних чисел"])
        self.assertNotIn(" 7", lay.body_text.splitlines()[0])
        self.assertEqual(lines[0].zone, "header")
        self.assertEqual(lines[1].zone, "body")

    def test_page_number_in_footer(self):
        lines = [line("Текст вправи", 600), line("23", 1300)]
        lay = analyze_page(lines, pdf_page=23, page_height=PAGE_H)
        self.assertEqual(lay.detected_book_page, 23)
        self.assertEqual(lay.body_text, "Текст вправи")
        self.assertEqual(len(lay.footer_lines), 1)

    def test_text_at_bottom_stays_in_body(self):
        lay = analyze_page([line("ділянках?", 1300)], pdf_page=7, page_height=PAGE_H)
        self.assertEqual(lay.body_text, "ділянках?")
        self.assertEqual(lay.footer_lines, [])

    def test_number_like_line_in_middle_stays(self):
        lay = analyze_page([line("12", 600)], pdf_page=7, page_height=PAGE_H)
        self.assertEqual(lay.body_text, "12")
        self.assertIsNone(lay.detected_book_page)

    def test_roundtrip(self):
        lay = analyze_page([line("Назва 7", 110), line("Текст", 500)], 7, PAGE_H)
        self.assertEqual(PageLayout.from_dict(lay.to_dict()), lay)


class DocumentTests(unittest.TestCase):
    def test_infer_book_pages_fixes_misread_and_missing(self):
        detected = {5: 5, 6: 6, 7: None, 8: 3, 9: 9}     # 7 — не прочитано, 8 → «3» (помилка 3/8)
        self.assertEqual(infer_book_pages(detected), {5: 5, 6: 6, 7: 7, 8: 8, 9: 9})

    def test_infer_book_pages_with_offset(self):
        self.assertEqual(infer_book_pages({10: 8, 11: 9, 12: None}), {10: 8, 11: 9, 12: 10})

    def test_infer_book_pages_nothing_detected(self):
        self.assertEqual(infer_book_pages({1: None, 2: None}), {1: None, 2: None})

    def test_headers_stored_once(self):
        def lay(page, title):
            return PageLayout(pdf_page=page, page_height=PAGE_H, header_title=title)
        layouts = [lay(6, "§ 1. Натуральні числа"), lay(7, "2. Цифри. Десятковий запис"),
                   lay(8, "§ 1. Натуральні числа"), lay(9, "2. Цифри. Десятковий заппс"),   # OCR-помилка
                   lay(10, "§ 1. Натуральні числа"), lay(11, "")]
        heads = collect_running_headers(layouts)
        self.assertEqual([(h.title, h.pages) for h in heads], [
            ("§ 1. Натуральні числа", [6, 8, 10]),
            ("2. Цифри. Десятковий запис", [7, 9]),
        ])

    def test_analyze_document(self):
        def ocr(page, header):
            words = [Word(t, BBox(130 + i * 50, 110, 170 + i * 50, 130), 90.0, 1, 1, 1)
                     for i, t in enumerate(header.split())]
            words.append(Word("Текст", BBox(130, 500, 200, 520), 90.0, 2, 1, 1))
            return PageOcr(PageImage(page, Path(f"p-{page}.png"), 886, PAGE_H, 152.0), words, "fake")
        layouts, heads = analyze_document([ocr(6, "6 51. Натуральні числа"),
                                           ocr(8, "8 51. Натуральні числа"),
                                           ocr(10, "1O 51. Натуральні числа")])   # «1O» — не число
        self.assertEqual([lay.book_page for lay in layouts], [6, 8, 10])
        self.assertEqual(len(heads), 1)
        self.assertEqual(heads[0].title, "§ 1. Натуральні числа")
        self.assertTrue(all(lay.body_text == "Текст" for lay in layouts))


if __name__ == "__main__":
    unittest.main()
