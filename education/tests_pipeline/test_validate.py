"""Фаза 14: перевірки дерева (validate.py) і HTML-звіт (report.py)."""
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from education.pdf_pipeline.datatypes import BBox, Line, Node, SourceRef, Word
from education.pdf_pipeline.layout import PageLayout
from education.pdf_pipeline.output.report import crop_png_b64, render_report, write_report
from education.pdf_pipeline.structure import ParseIssue
from education.pdf_pipeline.output.validate import (
    Problem, check_answer_mismatch, check_block_length, check_empty_nodes, check_exercise_numbers,
    check_expressions, check_figures, check_item_titles, check_lookalikes, check_low_conf_lines,
    check_orphan_answers, check_pages_without_body, from_parse_issues, tree_stats, validate,
)


def src(page=7):
    return SourceRef(page, page, BBox(10, 10, 200, 40))


def lesson_tree(numbers=(1, 2, 3), oral=()):
    root = Node("textbook", title="Тест")
    item = root.add(Node("item", number="1", title="Ряд натуральних чисел", source=src(),
                         data={"ocr_title": "Ряд натуральних чисел"}))
    if oral:
        ob = item.add(Node("block", data={"block_type": "oral_exercise"}))
        for n in oral:
            ob.add(Node("exercise", number=str(n), text="усна", source=src()))
    block = item.add(Node("block", data={"block_type": "exercise"}))
    for n in numbers:
        block.add(Node("exercise", number=str(n), text=f"вправа {n}", source=src()))
    return root, item, block


def make_line(text, conf=90.0, line_id=0):
    words = [Word(t, BBox(10 + 40 * i, 10, 45 + 40 * i, 30), conf) for i, t in enumerate(text.split())]
    return Line(words, page_index=7, line_id=line_id)


class ProblemTests(unittest.TestCase):
    def test_bad_severity(self):
        with self.assertRaises(ValueError):
            Problem("x", "fatal", "")

    def test_sort_errors_first(self):
        probs = validate(lesson_tree((1, 3, 3))[0])
        self.assertEqual(probs[0].severity, "error")


class TreeChecksTests(unittest.TestCase):
    def test_empty_node(self):
        root, item, block = lesson_tree()
        block.add(Node("exercise", number="4"))
        codes = [(p.code, p.node_path) for p in check_empty_nodes(root)]
        self.assertEqual(codes, [("empty_node", "п.1 / exercise / №4")])

    def test_missing_and_duplicate_numbers(self):
        root, *_ = lesson_tree((1, 2, 5, 5, 6))
        probs = check_exercise_numbers(root)
        self.assertEqual([p.code for p in probs], ["missing_exercise_number", "duplicate_exercise_number"])
        self.assertEqual(probs[0].data["missing"], [3, 4])

    def test_oral_numbers_do_not_count(self):
        root, *_ = lesson_tree((10, 11), oral=(1, 2))
        self.assertEqual(check_exercise_numbers(root), [])

    def test_item_title_mismatch(self):
        root, item, _ = lesson_tree()
        self.assertEqual(check_item_titles(root), [])
        item.data["ocr_title"] = "Відрізок. Довжина відрізка"
        self.assertEqual(check_item_titles(root)[0].code, "item_title_mismatch")

    def test_expressions(self):
        root, _, block = lesson_tree()
        ex = block.children[0]
        ex.add(Node("subexercise", number="1", text="12:5-4 1",
                    data={"expr_status": "malformed", "expr": "12 : 5 − 4 1", "expr_issues": ["missing_operator"]}))
        ex.add(Node("subexercise", number="2", text="98:34", data={"expr_status": "suspect", "expr": "98 : 34"}))
        ex.add(Node("subexercise", number="3", text="2+2", data={"expr_status": "ok"}))
        probs = check_expressions(root)
        self.assertEqual([(p.code, p.severity) for p in probs], [("expr_malformed", "error"), ("expr_suspect", "info")])
        self.assertEqual(probs[0].source.pdf_page, 7)        # джерело взято від вправи

    def test_answer_mismatch(self):
        root, _, block = lesson_tree()
        block.children[0].data.update(answer_mismatch=True, answer="4", answer_book="5")
        self.assertIn("у книзі 5", check_answer_mismatch(root)[0].message)

    def test_orphan_answer_only_inside_tree_range(self):
        root, *_ = lesson_tree((10, 11, 13))
        probs = check_orphan_answers(root, [10, 12, 13, 500])
        self.assertEqual([p.data["number"] for p in probs], [12])

    def test_figures(self):
        root, item, block = lesson_tree()
        item.add(Node("figure", data={"figure_id": "p007_y100"}))
        block.children[0].data["missing_figures"] = ["5"]
        probs = check_figures(root, ["p007_y100", "p008_y300"])
        self.assertEqual([p.code for p in probs], ["orphan_figure", "missing_figure"])
        self.assertEqual(probs[0].data["figure_id"], "p008_y300")

    def test_lookalike_left(self):
        root, _, block = lesson_tree()
        block.children[0].data["condition"] = "3Haiiдіть довжину AB"
        probs = check_lookalikes(root)
        self.assertEqual(len(probs), 1)
        self.assertEqual(probs[0].data["words"], ["Haiiдіть"])   # «AB» — чиста латиниця, не чіпаємо

    def test_block_too_long(self):
        root, item, _ = lesson_tree()
        item.add(Node("block", text="x", data={"block_type": "history_aside", "line_keys": [[7, i] for i in range(120)]}))
        probs = check_block_length(root, max_lines=90)
        self.assertEqual(probs[0].data["lines"], 120)
        self.assertEqual(check_block_length(root, max_lines=200), [])


class PageChecksTests(unittest.TestCase):
    def layout(self, lines, page=7):
        return PageLayout(pdf_page=page, page_height=1000, body_lines=lines, book_page=page)

    def test_low_conf(self):
        lay = self.layout([make_line("гарний рядок", 95), make_line("п0г4ний", 30, 1)])
        probs = check_low_conf_lines([lay])
        self.assertEqual([p.text for p in probs], ["п0г4ний"])
        self.assertEqual(probs[0].source.line_ids, (1,))

    def test_page_without_body(self):
        lays = [self.layout([], 1), self.layout([], 2), self.layout([make_line("текст")], 3)]
        self.assertEqual([p.pdf_page for p in check_pages_without_body(lays, skip_pages={1})], [2])

    def test_parse_issues(self):
        probs = from_parse_issues([ParseIssue("empty_block", "Порожній блок", 9),
                                   ParseIssue("weird_state", "Щось нове", 9),
                                   ParseIssue("exercise_number_gap", "Очікували 47", 9)])
        self.assertEqual([p.code for p in probs], ["empty_block", "unknown_transition"])


class ReportTests(unittest.TestCase):
    def test_crop(self):
        img = np.full((100, 200, 3), 255, np.uint8)
        self.assertTrue(crop_png_b64(img, BBox(10, 10, 50, 50)))
        self.assertEqual(crop_png_b64(img, BBox(500, 500, 600, 600)), "")

    def test_report(self):
        root, _, block = lesson_tree((1, 3))
        block.children[1].needs_review = True
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "p7.png"
            cv2.imwrite(str(page), np.full((300, 300, 3), 200, np.uint8))
            probs = validate(root)
            html = render_report(root, probs, tree_stats(root), page_images={7: page},
                                 norm_stats={"latin_lookalike": 3})
            self.assertIn("missing_exercise_number", html)
            self.assertIn("data:image/png;base64,", html)
            self.assertIn('class="leaf review"', html)
            self.assertIn("latin_lookalike", html)
            self.assertNotIn("<script src", html)                  # без зовнішніх залежностей
            out = write_report(Path(tmp) / "r" / "report.html", root, probs, tree_stats(root))
            self.assertTrue(out.exists())

    def test_html_escaped(self):
        root, _, block = lesson_tree()
        block.children[0].text = "<b>3 < 5</b>"
        self.assertIn("&lt;b&gt;3 &lt; 5", render_report(root, [], {}))


if __name__ == "__main__":
    unittest.main()
