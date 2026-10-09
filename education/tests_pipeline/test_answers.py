"""Фаза 13: розбір «ВІДПОВІДЕЙ» Тарасенкової і прив'язка до вправ."""
import unittest
from fractions import Fraction

from education.pdf_pipeline.answers import (
    AnswerEntry, AnswerKey, attach_answers, clean_value, paragraph_marker,
    parse_answer_lines, split_parts, to_number,
)
from education.pdf_pipeline.datatypes import Node

# Справжні рядки OCR зі стор. PDF 287 (fast-моделі, без виправлень).
PAGE_287 = [
    "ВІДПОВІДІ ри",
    "РОЗДІЛ 1 ————",
    "§ 1",
    "10. 1) 12: 16,20; 3)12; 13.11. 1) 18; 24: 30; 3) 30. 12. 1)4: 3) 7. 15. 1)11;",
    "13;23.16.1)29:37.17.1)7; 13; 19;31;37:43.18.1)4.21. 1) Так, Зкороб-",
    "ки; 3) так, б коробок. 22. 1) Так, по 18 осіб; 3) ні. 23. 3) 16; 32; 48; 64; 80; 96;",
    "4) 22; 44; 66; 88. 24. 3) 12; 24; 36; 48; 60; 72: 84; 96; 4) 15; 30; 45; б0; 75; 90.",
    "25. 105; 140; 175; 210; 245; 280; 315; 350; 385. 26. 24; 48; 72; 96. 27. 1) Hi:",
    "2) ні; 3) так. 28.Наприклад, 4; 9; 25; 49.29. Наприклад, б; 10:14,21.30.13",
    "111.31. 1) Так, 45 монет; 3) так, 9 монет. 32. 15 років, 33 роки, 55 років.",
    "82",
    "41. 1) 6; 2) 9. 42. 1) 3; 2) 5.",
]


def lines(texts, page=287):
    return [(page, t) for t in texts]


class ParagraphMarkerTests(unittest.TestCase):
    def test_ocr_variants(self):
        cases = [("§ 1", None, 1), ("82", 1, 2), ("856", 5, 6), ("8512", 11, 12), ("510", 8, 10),
                 ("58", 7, 8), ("8 34", 33, 34), ("§ 23 ЛЕП", 22, 23), ("§7", 6, 7)]
        for text, current, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(paragraph_marker(text, current), expected)

    def test_rejects_unexpected_numbers(self):
        self.assertIsNone(paragraph_marker("5 29", 6))   # сміття між § 6 і § 7
        self.assertIsNone(paragraph_marker("82", 10))    # назад не йдемо
        self.assertIsNone(paragraph_marker("§ 5", None))  # перший § — лише 1


class ValueTests(unittest.TestCase):
    def test_clean_value(self):
        self.assertEqual(clean_value(" 4: "), "4")
        self.assertEqual(clean_value("545 679; Рис. 224"), "545 679")      # підпис рисунка не частина відповіді
        self.assertEqual(clean_value("Hi"), "ні")
        self.assertEqual(clean_value("- 36"), "-36")

    def test_split_parts(self):
        self.assertEqual(split_parts("1) 4; 2) 98; 3) 16."), {"1": "4", "2": "98", "3": "16"})
        self.assertEqual(split_parts("Збільшилась на 5 учнів."), {"": "Збільшилась на 5 учнів"})

    def test_to_number(self):
        self.assertEqual(to_number("80,09"), Fraction(8009, 100))
        self.assertEqual(to_number("-3,1"), Fraction(-31, 10))
        self.assertIsNone(to_number("так"))


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.key = parse_answer_lines(lines(PAGE_287))

    def test_numbers_inside_values_are_not_exercises(self):
        # «3) 30. 12.» — 30 тут значення, а не вправа; жадібний вибір втратив би 12…29.
        for n in (10, 11, 12, 15, 16, 17, 18, 21, 22, 29, 30, 31, 32):
            self.assertIn(n, self.key.entries, n)
        self.assertEqual(self.key.get(11).parts, {"1": "18; 24; 30", "3": "30"})
        self.assertEqual(self.key.get(12).parts, {"1": "4", "3": "7"})

    def test_paragraphs(self):
        self.assertEqual(self.key.get(10).paragraph, 1)
        self.assertEqual(self.key.get(41).paragraph, 2)
        self.assertEqual(self.key.get(10).pdf_page, 287)

    def test_section_heading_ignored(self):
        self.assertNotIn(1, self.key.entries)

    def test_ocr_fixes_in_values(self):
        self.assertEqual(self.key.get(21).parts["3"], "так, 6 коробок")
        self.assertEqual(self.key.get(27).parts["1"], "ні")


class AttachTests(unittest.TestCase):
    def tree(self):
        root = Node("textbook")
        oral = root.add(Node("block", data={"block_type": "oral_exercise"}))
        oral.add(Node("exercise", number="5"))
        block = root.add(Node("block", data={"block_type": "exercise"}))
        ex = block.add(Node("exercise", number="5"))
        s1 = ex.add(Node("subexercise", number="1", text="2 + 2"))
        s1.data["answer"] = "4"
        s2 = ex.add(Node("subexercise", number="2", text="3 + 3"))
        s2.data["answer"] = "7"          # «обчислено» неправильно → розбіжність
        block.add(Node("exercise", number="6"))
        return root, oral.children[0], s1, s2, block.children[1]

    def test_attach_and_verify(self):
        root, oral_ex, s1, s2, ex6 = self.tree()
        key = AnswerKey(entries={
            5: AnswerEntry(5, 1, 287, "1) 4; 2) 6", {"1": "4", "2": "6"}),
            6: AnswerEntry(6, 1, 287, "так", {"": "так"}),
            99: AnswerEntry(99, 1, 287, "1", {"": "1"}),
        })
        stats = attach_answers(root, key)
        self.assertTrue(s1.data["answer_verified"])
        self.assertTrue(s2.data["answer_mismatch"])
        self.assertTrue(s2.needs_review)
        self.assertEqual(ex6.data["answer_book"], "так")
        self.assertNotIn("answer_book_raw", oral_ex.data)   # усні не чіпаємо
        self.assertEqual((stats.exercises_with_answers, stats.verified, stats.mismatched,
                          stats.unknown_numbers), (2, 1, 1, 1))


if __name__ == "__main__":
    unittest.main()
