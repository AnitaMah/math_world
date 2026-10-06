"""Тести для сіток підпунктів (grids.py) — на реальних рядках зі стор. 7 Мерзляка."""
import unittest

from education.pdf_pipeline.datatypes import BBox, Line, Word
from education.pdf_pipeline.grids import find_grids, read_grid, split_cells


def line(*cells, y=0):
    """line((x, "1) 238 + 435;"), (317, "4) 2000 − 546;")) — слова кожної клітинки йдуть від x."""
    words = []
    for x, text in cells:
        for i, t in enumerate(text.split()):
            words.append(Word(t, BBox(x + i * 30, y, x + i * 30 + 25, y + 18), 90.0))
    return Line(words=words, page_index=7)


EX12 = [   # вправа 12 так, як її прочитав OCR (з помилкою «9)» замість «5)»)
    line((104, "1) 238 + 435;"), (317, "4) 2000 − 546;"), (529, "7) 98 - 34;"), y=0),
    line((103, "2) 4385 + 2697;"), (317, "9) 3400 − 896;"), (528, "8) 645 - 36."), y=25),
    line((103, "3) 843 − 457;"), (317, "6) 23 - 46;"), y=50),
]


class SplitCellsTests(unittest.TestCase):
    def test_glued_marker(self):
        _, cells = split_cells(line((104, "1) 13 28;"), (317, "2)291i111?")), row=0)
        self.assertEqual([(c.raw_label, c.text) for c in cells], [("1", "13 28;"), ("2", "291i111?")])

    def test_marker_inside_sentence_is_ignored(self):
        prefix, cells = split_cells(line((79, "17. У квадраті (рис. 1) суми чисел")), row=0)
        self.assertEqual(cells, [])
        self.assertEqual(len(prefix), 7)

    def test_prefix_before_first_marker(self):
        prefix, cells = split_cells(line((79, "12. Обчисліть: 1) 2 + 3;")), row=0)
        self.assertEqual([w.text for w in prefix], ["12.", "Обчисліть:"])
        self.assertEqual(cells[0].text, "2 + 3;")


class ReadGridTests(unittest.TestCase):
    def test_exercise_12_column_order_and_fix(self):
        grid = read_grid(EX12, [0, 1, 2])
        self.assertEqual(grid.order, "column")
        self.assertEqual(grid.n_columns, 3)
        self.assertEqual([c.label for c in grid.cells], ["1", "2", "3", "4", "5", "6", "7", "8"])
        self.assertEqual(grid.cells[3].text, "2000 − 546;")
        fixed = [c for c in grid.cells if c.ocr_fixed]
        self.assertEqual([(c.raw_label, c.label) for c in fixed], [("9", "5")])
        self.assertFalse(grid.needs_review)

    def test_exercise_14_two_columns(self):
        lines = [line((104, "1) 43 + 24 · 58 − 39;"), (420, "3) 43 + 24 · (58 − 39);"), y=0),
                 line((103, "2) (43 + 24) · 58 − 39;"), (420, "4) (43 + 24) · (58 − 39)."), y=25)]
        grid = read_grid(lines, [0, 1])
        self.assertEqual([c.label for c in grid.cells], ["1", "2", "3", "4"])
        self.assertTrue(grid.cells[2].text.startswith("43 + 24 · (58"))

    def test_row_major_grid(self):
        lines = [line((100, "1) a;"), (300, "2) b;"), y=0), line((100, "3) c;"), (300, "4) d."), y=25)]
        grid = read_grid(lines, [0, 1])
        self.assertEqual(grid.order, "row")
        self.assertEqual([c.text for c in grid.cells], ["a;", "b;", "c;", "d."])

    def test_ocr_extra_digit(self):
        lines = [line((100, "1) a;"), (300, "17) b;"), y=0)]   # «17)» замість «2)»
        grid = read_grid(lines, [0])
        self.assertEqual([c.label for c in grid.cells], ["1", "2"])
        self.assertTrue(grid.cells[1].ocr_fixed)

    def test_letter_b_read_as_digit(self):
        lines = [line((100, "5) a;"), y=0), line((100, "б) b;"), y=25)]  # «б)» = «6)»
        lines.insert(0, line((100, "4) z;"), y=-25))
        grid = read_grid(lines, [0, 1, 2])
        self.assertEqual([c.label for c in grid.cells], ["4", "5", "6"])

    def test_real_letter_list_is_kept(self):
        lines = [line((100, "а) x;"), (300, "в) z;"), y=0), line((100, "б) y;"), (300, "г) w."), y=25)]
        grid = read_grid(lines, [0, 1])
        self.assertEqual([c.label for c in grid.cells], ["а", "б", "в", "г"])

    def test_mostly_garbage_needs_review(self):
        lines = [line((100, "7) a;"), (300, "9) b;"), (500, "3) c;"), y=0)]
        self.assertTrue(read_grid(lines, [0]).needs_review)


class FindGridsTests(unittest.TestCase):
    def test_finds_runs_between_text(self):
        lines = [line((79, "12. Обчисліть:"), y=-25), *EX12, line((79, "13. Назва «Україна»"), y=75)]
        grids = find_grids(lines)
        self.assertEqual(len(grids), 1)
        self.assertEqual(grids[0].line_indices, [1, 2, 3])

    def test_single_line_with_two_markers(self):
        grids = find_grids([line((104, "1) 6 і 24;"), (317, "2) 18 і 81?"))])
        self.assertEqual([c.text for c in grids[0].cells], ["6 і 24;", "18 і 81?"])

    def test_single_marker_line_alone_is_not_grid(self):
        self.assertEqual(find_grids([line((104, "1) лише один пункт"))]), [])


if __name__ == "__main__":
    unittest.main()
