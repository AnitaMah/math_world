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


class NoiseAndRegionTests(unittest.TestCase):
    def test_icon_noise_removed(self):
        from education.pdf_pipeline.layout import strip_edge_noise
        ln = Line(words=[Word("2", BBox(77, 0, 90, 20), 21.0), Word("Задача", BBox(161, 0, 230, 20), 96.0),
                         Word("Сови", BBox(361, 0, 400, 20), 94.0)], page_index=7)
        self.assertEqual(strip_edge_noise(ln).text, "Задача Сови")

    def test_confident_short_word_kept(self):
        from education.pdf_pipeline.layout import strip_edge_noise
        ln = Line(words=[Word("17.", BBox(0, 0, 30, 20), 96.0), Word("У", BBox(40, 0, 50, 20), 96.0)], page_index=1)
        self.assertEqual(strip_edge_noise(ln).text, "17. У")

    def test_figure_frame_removes_numbers_from_body(self):
        lines = [line("17. У квадраті суми чисел", 940), line("10 9 13", 960, x=650)]
        lay = analyze_page(lines, 7, PAGE_H, frames=[BBox(635, 933, 755, 1055)])
        self.assertEqual([r.kind for r in lay.regions], ["figure"])
        self.assertEqual(lay.body_text, "17. У квадраті суми чисел")
        self.assertEqual([ln.text for ln in lay.figure_lines], ["10 9 13"])

    def test_text_frame_is_boxed(self):
        lines = [line("Зверніть увагу: серед чисел парні діляться", 400, x=80)]
        lay = analyze_page(lines, 11, PAGE_H, frames=[BBox(66, 368, 900, 460)])
        self.assertEqual(lay.regions[0].kind, "boxed")
        self.assertEqual(lay.body_lines[0].zone, "boxed")

    def test_caption_attached(self):
        lines = [line("Рис. 1", 1070, x=660)]
        lay = analyze_page(lines, 7, PAGE_H, frames=[BBox(635, 933, 755, 1055)])
        self.assertEqual(lay.regions[0].caption, "Рис. 1")

    def test_detect_frames_on_synthetic_image(self):
        import numpy as np
        import cv2
        from education.pdf_pipeline.layout.regions import detect_frames
        img = np.full((1000, 800), 255, np.uint8)
        cv2.rectangle(img, (100, 200), (500, 400), 0, 2)          # рамка
        cv2.putText(img, "text", (120, 300), cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 2)
        cv2.putText(img, "outside", (100, 700), cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 2)
        frames = detect_frames(img)
        self.assertEqual(len(frames), 1)
        self.assertAlmostEqual(frames[0].x0, 100, delta=3)
        self.assertAlmostEqual(frames[0].y1, 401, delta=3)


class OffsetChangeTests(unittest.TestCase):
    def test_offset_changes_inside_book(self):
        # Сторінки 1–20: номер = PDF; з 21-ї вставлено 9 ненумерованих → номер = PDF − 9.
        detected = {p: p for p in range(1, 21)}
        detected.update({p: p - 9 for p in range(30, 50)})
        detected[10] = None
        detected[40] = 36          # помилка OCR (3 ↔ 8: має бути 31)
        fixed = infer_book_pages(detected)
        self.assertEqual(fixed[10], 10)
        self.assertEqual(fixed[40], 31)
        self.assertEqual(fixed[5], 5)
        self.assertEqual(fixed[45], 36)
