"""Тести для education.pdf_pipeline.exercises."""
import unittest

import cv2
import numpy as np

from education.pdf_pipeline.datatypes import BBox, Line, Node, Word
from education.pdf_pipeline.exercises import (
    classify_task, detect_difficulty_mark, enrich_exercises, figure_refs, flag_difficulty_order,
    has_margin_icon, is_colored, is_figure_label_line, split_exercise,
)
from education.pdf_pipeline.layout import PageLayout
from education.pdf_pipeline.profiles import get_profile


def line(*cells, y=0, line_id=0):
    """line((x, "текст"), …) — слова кожного шматка йдуть від x з кроком 30 px."""
    words = []
    for x, text in cells:
        for i, t in enumerate(text.split()):
            words.append(Word(t, BBox(x + i * 30, y, x + i * 30 + 25, y + 18), 90.0))
    return Line(words=words, page_index=7, line_id=line_id)


class SplitExerciseTests(unittest.TestCase):
    def test_exercise_12_grid(self):
        lines = [
            line((79, "12. Обчисліть:"), y=0),
            line((104, "1) 238 + 435;"), (317, "4) 2000 − 546;"), (529, "7) 98 · 34;"), y=25),
            line((103, "2) 4385 + 2697;"), (317, "5) 3400 − 896;"), (528, "8) 645 · 36."), y=50),
            line((103, "3) 843 − 457;"), (317, "6) 23 · 46;"), y=75),
        ]
        split = split_exercise(lines, "Обчисліть:")
        self.assertEqual(split.condition, "Обчисліть:")
        self.assertEqual([c.label for c in split.cells], ["1", "2", "3", "4", "5", "6", "7", "8"])
        self.assertEqual(split.cells[4].text, "3400 − 896;")

    def test_inline_subitems_after_colon(self):
        lines = [line((80, "31. Чи могла вона отримати здачу монетами: 1) по 5 к.;"), y=0),
                 line((100, "2) по 10 к.; 3) по 25 к.?"), y=25)]
        split = split_exercise(lines, "Чи могла вона отримати здачу монетами: 1) по 5 к.;")
        self.assertEqual(split.condition, "Чи могла вона отримати здачу монетами:")
        self.assertEqual([(c.label, c.text) for c in split.cells], [("1", "по 5 к.;"), ("2", "по 10 к.;"), ("3", "по 25 к.?")])

    def test_wrapped_subitem_and_tail(self):
        lines = [line((80, "65. Чи можна записати числа, які:"), y=0),
                 line((100, "1) діляться на 2;"), (330, "3) діляться на 5 і"), y=25),
                 line((100, "2) не діляться на 2;"), (330, "4) діляться на 10?"), y=50),
                 line((100, "Якщо так, то наведіть приклади."), y=75)]
        split = split_exercise(lines, "Чи можна записати числа, які:")
        self.assertEqual(len(split.cells), 4)
        self.assertEqual(split.tail, "Якщо так, то наведіть приклади.")

    def test_figure_labels_removed(self):
        lines = [line((77, "45. Назвіть усі відрізки, зображені на рисунку 15."), y=0),
                 line((200, "А N ер К е R"), y=25)]
        split = split_exercise(lines, "Назвіть усі відрізки, зображені на рисунку 15.")
        self.assertEqual(split.condition, "Назвіть усі відрізки, зображені на рисунку 15.")
        self.assertEqual(split.figure_labels, "А N ер К е R")

    def test_is_figure_label_line(self):
        self.assertTrue(is_figure_label_line(line((0, "А В С D"))))
        self.assertFalse(is_figure_label_line(line((0, "щоб він позначав ряд"))))
        self.assertFalse(is_figure_label_line(line((0, "1) 34; 2) 246;"))))


class ClassifyTests(unittest.TestCase):
    def test_kinds(self):
        cases = {
            "Обчисліть:": ("compute", "number"),
            "Виконайте дії:": ("compute", "number"),
            "Порівняйте числа:": ("compare", "comparison"),
            "Накресліть відрізок АВ завдовжки 5 см.": ("construction", "none"),
            "Розташуйте в порядку зростання числа:": ("order", "sequence"),
            "Назвіть 14 перших натуральних чисел.": ("name", "text"),
            "Чи правильно, що парним є число:": ("other", "yes_no"),
        }
        for text, (task, answer) in cases.items():
            with self.subTest(text=text):
                got = classify_task(text, has_subitems=True)
                self.assertEqual((got["task_verb"], got["answer_kind"]), (task, answer))

    def test_word_problem(self):
        text = "На сніданок Карлсон з'їв 26 банок варення, а на обід — на 16 банок більше. Скільки кг варення він з'їв?"
        got = classify_task(text, has_subitems=False)
        self.assertTrue(got["is_word_problem"])
        self.assertTrue(got["auto_checkable"])
        self.assertFalse(classify_task("Обчисліть:", has_subitems=True)["is_word_problem"])

    def test_figure_refs(self):
        self.assertEqual(figure_refs("Порівняйте відрізки АВ і СD (рис. 17) та рис. 5"), ["5", "17"])
        self.assertEqual(figure_refs("без рисунків"), [])


def blank(h=60, w=200, color=False):
    return np.full((h, w, 3) if color else (h, w), 255, np.uint8)


class ImageMarkTests(unittest.TestCase):
    NUMBER = BBox(20, 30, 40, 48)   # цифри номера: 20×18 px
    NEXT = BBox(70, 30, 150, 48)

    def page_with_number(self):
        img = blank()
        cv2.rectangle(img, (20, 30), (38, 52), 0, -1)          # «цифри» — йдуть до низу смуги
        return img

    def test_ring(self):
        img = self.page_with_number()
        cv2.circle(img, (47, 27), 3, 0, 1)                      # ◦ над рядком, справа від номера
        self.assertEqual(detect_difficulty_mark(img, self.NUMBER, self.NEXT), "◦")

    def test_one_and_two_dots(self):
        img = self.page_with_number()
        cv2.circle(img, (47, 30), 2, 0, -1)
        self.assertEqual(detect_difficulty_mark(img, self.NUMBER, self.NEXT), "•")
        cv2.circle(img, (54, 30), 2, 0, -1)
        self.assertEqual(detect_difficulty_mark(img, self.NUMBER, self.NEXT), "••")

    def test_star(self):
        img = self.page_with_number()
        for dx, dy in ((4, 0), (0, 4), (3, 3), (3, -3)):
            cv2.line(img, (50 - dx, 29 - dy), (50 + dx, 29 + dy), 0, 1)
        self.assertEqual(detect_difficulty_mark(img, self.NUMBER, self.NEXT), "*")

    def test_no_mark(self):
        self.assertIsNone(detect_difficulty_mark(self.page_with_number(), self.NUMBER, self.NEXT))

    def test_colored_number(self):
        img = blank(color=True)
        cv2.rectangle(img, (20, 30), (38, 48), (60, 170, 60), -1)   # BGR зелений
        self.assertTrue(is_colored(img, self.NUMBER))
        cv2.rectangle(img, (20, 30), (38, 48), (20, 20, 20), -1)    # чорний
        self.assertFalse(is_colored(img, self.NUMBER))

    def test_margin_icon(self):
        img = blank(h=100, w=300)
        number = BBox(100, 40, 130, 58)
        self.assertFalse(has_margin_icon(img, number))
        cv2.rectangle(img, (55, 35), (85, 70), 0, -1)              # «будиночок» на полі
        self.assertTrue(has_margin_icon(img, number))


class DifficultyOrderTests(unittest.TestCase):
    def test_flags_level_drop(self):
        block = Node("block", data={"block_type": "exercise"})
        for num, level in [("60", "medium"), ("61", "olympiad"), ("62", "sufficient"), ("63", "sufficient")]:
            block.add(Node("exercise", number=num, data={"difficulty": level}))
        root = Node("textbook")
        root.add(block)
        self.assertEqual(flag_difficulty_order(root), 1)
        self.assertTrue(block.children[1].needs_review)
        self.assertFalse(block.children[0].needs_review)


class EnrichTests(unittest.TestCase):
    def test_enrich_without_images(self):
        lines = [
            line((79, "12. Обчисліть:"), y=0, line_id=0),
            line((104, "1) 2 + 3;"), (317, "3) 4 + 5;"), y=25, line_id=1),
            line((103, "2) 6 + 7;"), (317, "4) 8 + 9."), y=50, line_id=2),
        ]
        layout = PageLayout(pdf_page=7, page_height=1329, body_lines=lines)
        root = Node("textbook")
        block = root.add(Node("block", data={"block_type": "review_exercise"}))
        block.add(Node("exercise", number="12", text="Обчисліть:\n1) 2 + 3; 3) 4 + 5;\n2) 6 + 7; 4) 8 + 9.",
                       data={"difficulty": None, "line_keys": [[7, 0], [7, 1], [7, 2]]}))
        stats = enrich_exercises(root, [layout], get_profile("math_merzlyak_5"))
        ex = root.find("exercise")[0]
        self.assertEqual(ex.data["condition"], "Обчисліть:")
        self.assertEqual([(s.number, s.text) for s in ex.find("subexercise")],
                         [("1", "2 + 3;"), ("2", "6 + 7;"), ("3", "4 + 5;"), ("4", "8 + 9.")])
        self.assertEqual(ex.data["task_verb"], "compute")
        self.assertFalse(ex.data["homework"])
        self.assertEqual((stats.exercises, stats.with_subitems, stats.subitems), (1, 1, 4))

    def test_rerun_does_not_duplicate_subitems(self):
        lines = [line((79, "1. Обчисліть:"), y=0, line_id=0), line((104, "1) 2;"), (300, "2) 3."), y=25, line_id=1)]
        layout = PageLayout(pdf_page=5, page_height=1329, body_lines=lines)
        root = Node("textbook")
        root.add(Node("block", data={"block_type": "exercise"})).add(
            Node("exercise", number="1", text="Обчисліть:", data={"line_keys": [[5, 0], [5, 1]]}))
        profile = get_profile("math_tarasenkova_6")
        enrich_exercises(root, [layout], profile)
        enrich_exercises(root, [layout], profile)
        self.assertEqual(len(root.find("subexercise")), 2)


if __name__ == "__main__":
    unittest.main()
