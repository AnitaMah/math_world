"""Тести для education.pdf_pipeline.figures — на згенерованих сторінках з «рисунками»."""
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from education.pdf_pipeline.datatypes import BBox, Line, Node, SourceRef, Word
from education.pdf_pipeline.figures import (
    Figure, attach_figures, extract_page_figures, find_captions, group_by_captions, is_caption_line,
)
from education.pdf_pipeline.layout import PageLayout


def text_line(text, x, y, h=14, line_id=0, conf=90.0):
    words = [Word(t, BBox(x + i * 60, y, x + i * 60 + 50, y + h), conf) for i, t in enumerate(text.split())]
    return Line(words=words, page_index=1, line_id=line_id)


def draw_text_block(img, line):
    """Імітує надрукований текст: чорні прямокутники на місці слів."""
    for w in line.words:
        cv2.rectangle(img, (w.bbox.x0, w.bbox.y0 + 3), (w.bbox.x1, w.bbox.y1 - 3), 0, -1)


class CaptionTests(unittest.TestCase):
    def test_find_captions(self):
        caps = find_captions([text_line("Рис. 27 Рис. 28", 100, 300), text_line("Puc. З", 100, 400),
                              text_line("див. рис. 5 нижче", 100, 500)])
        self.assertEqual([n for n, _ in caps], ["27", "28", "3", "5"])

    def test_is_caption_line(self):
        self.assertTrue(is_caption_line(text_line("Рис. 15", 0, 0)))
        self.assertFalse(is_caption_line(text_line("Порівняйте відрізки на рисунку 15 і поясніть чому", 0, 0)))


class GroupTests(unittest.TestCase):
    def test_subfigures_under_one_caption(self):
        regions = [BBox(100, 100, 200, 180), BBox(300, 100, 400, 180), BBox(100, 200, 200, 280)]
        caps = [("31", BBox(220, 300, 280, 314))]
        groups = group_by_captions(regions, caps, text_lines=[], text_height=14)
        self.assertEqual(groups, [(BBox(100, 100, 400, 280), "31")])

    def test_two_captions_in_row(self):
        regions = [BBox(100, 100, 300, 120), BBox(400, 100, 700, 120)]
        caps = [("27", BBox(180, 140, 240, 154)), ("28", BBox(520, 140, 580, 154))]
        groups = dict((n, b) for b, n in group_by_captions(regions, caps, [], 14))
        self.assertEqual(groups["27"], regions[0])
        self.assertEqual(groups["28"], regions[1])

    def test_text_between_breaks_link(self):
        regions = [BBox(100, 100, 300, 200)]
        caps = [("5", BBox(180, 400, 240, 414))]
        between = [text_line("Звичайний текст між ними", 100, 300)]
        groups = group_by_captions(regions, caps, between, 14)
        self.assertEqual(groups, [(regions[0], None)])


class ExtractTests(unittest.TestCase):
    def test_page_with_text_and_figure(self):
        img = np.full((800, 600), 255, np.uint8)
        lines = [text_line("Назвіть усі відрізки зображені на рисунку", 50, 100, line_id=0),
                 text_line("Рис. 15", 250, 420, line_id=2)]
        for ln in lines:
            draw_text_block(img, ln)
        cv2.line(img, (100, 250), (400, 380), 0, 2)              # рисунок: два відрізки
        cv2.line(img, (100, 380), (400, 250), 0, 2)
        layout = PageLayout(pdf_page=19, page_height=800, body_lines=lines)
        with tempfile.TemporaryDirectory() as tmp:
            figs = extract_page_figures(img, layout, Path(tmp))
            self.assertEqual(len(figs), 1)
            fig = figs[0]
            self.assertEqual(fig.number, "15")
            self.assertTrue(fig.bbox.x0 <= 100 and fig.bbox.x1 >= 400)
            self.assertTrue(fig.path.exists())
            self.assertEqual(fig.path.name, "p019_ris15.png")

    def test_heading_underline_is_not_figure(self):
        img = np.full((800, 600), 255, np.uint8)
        cv2.line(img, (60, 300), (360, 300), 0, 2)               # підкреслення «Вправи»
        layout = PageLayout(pdf_page=6, page_height=800, body_lines=[text_line("Текст абзацу тут", 50, 500)])
        self.assertEqual(extract_page_figures(img, layout), [])


class AttachTests(unittest.TestCase):
    def build(self):
        root = Node("textbook")
        item = root.add(Node("item", number="3", source=SourceRef(15)))
        theory = item.add(Node("block", data={"block_type": "theory"}))
        exercises = item.add(Node("block", data={"block_type": "exercise"}))
        ex45 = exercises.add(Node("exercise", number="45", source=SourceRef(19, bbox=BBox(70, 700, 800, 720)),
                                  data={"figure_refs": ["15"]}))
        ex17 = exercises.add(Node("exercise", number="17", source=SourceRef(7, bbox=BBox(70, 960, 600, 1060)),
                                  data={"figure_refs": ["1"]}))
        return root, theory, ex45, ex17

    def test_link_by_number_and_rest_to_theory(self):
        root, theory, ex45, _ = self.build()
        figs = [Figure(19, BBox(90, 730, 740, 830), "15"), Figure(16, BBox(300, 600, 600, 800), "6"),
                Figure(70, BBox(0, 0, 10, 10), "15")]            # той самий номер, але далеко — не той
        stats = attach_figures(root, figs)
        self.assertEqual([c.data["figure_id"] for c in ex45.children], ["p019_ris15"])
        self.assertIn("p016_ris6", [c.data["figure_id"] for c in theory.children])
        self.assertEqual(stats["linked"], 1)

    def test_unnumbered_figure_near_exercise(self):
        root, _, _, ex17 = self.build()
        figs = [Figure(7, BBox(632, 930, 758, 1057))]           # «Рис. 1» OCR не прочитав
        attach_figures(root, figs)
        self.assertEqual([c.number for c in ex17.children if c.kind == "figure"], ["1"])

    def test_missing(self):
        root, _, ex45, _ = self.build()
        stats = attach_figures(root, [])
        self.assertEqual(ex45.data["missing_figures"], ["15"])
        self.assertEqual(stats["missing"], 2)

    def test_rerun_no_duplicates(self):
        root, theory, ex45, _ = self.build()
        figs = [Figure(19, BBox(90, 730, 740, 830), "15"), Figure(16, BBox(300, 600, 600, 800), "6")]
        attach_figures(root, figs)
        attach_figures(root, figs)
        self.assertEqual(len(ex45.find("figure")), 1)
        self.assertEqual(len(theory.find("figure")), 1)


if __name__ == "__main__":
    unittest.main()
