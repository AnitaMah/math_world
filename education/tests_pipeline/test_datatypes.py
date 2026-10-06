"""Тести для education.pdf_pipeline.datatypes."""
import json
import unittest
from pathlib import Path

from education.pdf_pipeline.datatypes import (
    BBox, Line, Node, PageImage, PageOcr, SourceRef, Word, Zone,
)


def word(text: str, x0: int, y0: int, x1: int, y1: int, conf: float = 90.0) -> Word:
    return Word(text=text, bbox=BBox(x0, y0, x1, y1), conf=conf)


def roundtrip(obj):
    """to_dict → JSON-рядок → from_dict: перевіряє, що дані справді JSON-сумісні."""
    data = json.loads(json.dumps(obj.to_dict(), ensure_ascii=False))
    return type(obj).from_dict(data)


class BBoxTests(unittest.TestCase):
    def test_size_and_center(self):
        b = BBox(10, 20, 30, 60)
        self.assertEqual((b.width, b.height, b.area), (20, 40, 800))
        self.assertEqual(b.center, (20.0, 40.0))

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            BBox(30, 0, 10, 10)

    def test_zero_width_is_allowed(self):
        self.assertEqual(BBox(5, 5, 5, 10).width, 0)

    def test_union(self):
        self.assertEqual(BBox(0, 0, 10, 10).union(BBox(5, 5, 20, 15)), BBox(0, 0, 20, 15))

    def test_union_all(self):
        boxes = [BBox(0, 0, 1, 1), BBox(5, 5, 6, 6), BBox(2, -3, 3, 0)]
        self.assertEqual(BBox.union_all(boxes), BBox(0, -3, 6, 6))
        with self.assertRaises(ValueError):
            BBox.union_all([])

    def test_intersects_and_iou(self):
        a, b, far = BBox(0, 0, 10, 10), BBox(5, 0, 15, 10), BBox(100, 100, 110, 110)
        self.assertTrue(a.intersects(b))
        self.assertFalse(a.intersects(far))
        self.assertAlmostEqual(a.iou(b), 50 / 150)
        self.assertEqual(a.iou(a), 1.0)
        self.assertEqual(a.iou(far), 0.0)

    def test_touching_boxes_do_not_intersect(self):
        self.assertFalse(BBox(0, 0, 10, 10).intersects(BBox(10, 0, 20, 10)))

    def test_scale_and_shift(self):
        self.assertEqual(BBox(10, 20, 30, 40).scale(0.5), BBox(5, 10, 15, 20))
        self.assertEqual(BBox(0, 0, 10, 10).shift(5, -2), BBox(5, -2, 15, 8))

    def test_roundtrip(self):
        b = BBox(1, 2, 3, 4)
        self.assertEqual(roundtrip(b), b)
        self.assertEqual(b.to_dict(), [1, 2, 3, 4])


class WordTests(unittest.TestCase):
    def test_roundtrip(self):
        w = Word("Вправи", BBox(1, 2, 3, 4), 87.5, 1, 2, 3, 4, raw_text="Bправи")
        self.assertEqual(roundtrip(w), w)


class LineTests(unittest.TestCase):
    def setUp(self):
        self.line = Line(
            words=[word("12.", 0, 0, 30, 20, 95), word("Обчисліть:", 40, 2, 200, 24, 75)],
            page_index=7,
        )

    def test_text_and_bbox(self):
        self.assertEqual(self.line.text, "12. Обчисліть:")
        self.assertEqual(self.line.bbox, BBox(0, 0, 200, 24))

    def test_conf(self):
        self.assertEqual(self.line.conf, 85.0)
        self.assertEqual(self.line.min_conf, 75)

    def test_height_is_median(self):
        self.assertEqual(self.line.height, 21.0)

    def test_empty_line(self):
        empty = Line(words=[], page_index=1)
        self.assertEqual((empty.text, empty.conf, empty.min_conf, empty.height), ("", 0.0, 0.0, 0.0))

    def test_roundtrip(self):
        self.line.zone = "header"
        self.assertEqual(roundtrip(self.line), self.line)


class ZoneTests(unittest.TestCase):
    def test_roundtrip(self):
        z = Zone("boxed", BBox(0, 0, 100, 50), [Line([word("a", 0, 0, 5, 5)], 3)])
        self.assertEqual(roundtrip(z), z)


class PageTests(unittest.TestCase):
    def test_page_image_roundtrip(self):
        p = PageImage(7, Path("pipeline_cache/abc/pages/p-007.png"), 886, 1329, 152.0, False)
        self.assertEqual(roundtrip(p), p)

    def test_page_ocr_roundtrip(self):
        p = PageImage(7, Path("p-007.png"), 886, 1329, 152.0)
        ocr = PageOcr(p, [word("a", 0, 0, 5, 5)], "tesseract-5.5.3", {"psm": 6}, 1234)
        self.assertEqual(roundtrip(ocr), ocr)


class SourceRefTests(unittest.TestCase):
    def test_roundtrip_full_and_minimal(self):
        full = SourceRef(7, 7, BBox(0, 0, 10, 10), (3, 4, 5))
        minimal = SourceRef(1)
        self.assertEqual(roundtrip(full), full)
        self.assertEqual(roundtrip(minimal), minimal)


class NodeTests(unittest.TestCase):
    def build_tree(self) -> Node:
        root = Node("textbook", title="Математика 5")
        section = root.add(Node("section", number="I"))
        item = section.add(Node("item", number="2", title="Цифри"))
        block = item.add(Node("block", data={"block_type": "exercise"}))
        block.add(Node("exercise", number="8", source=SourceRef(7, 7, BBox(0, 0, 10, 10))))
        block.add(Node("exercise", number="9", needs_review=True))
        return root

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            Node("chapter")

    def test_add_returns_child(self):
        parent = Node("section")
        child = parent.add(Node("item"))
        self.assertIs(parent.children[0], child)

    def test_walk_is_depth_first(self):
        kinds = [n.kind for n in self.build_tree().walk()]
        self.assertEqual(kinds, ["textbook", "section", "item", "block", "exercise", "exercise"])

    def test_find(self):
        numbers = [n.number for n in self.build_tree().find("exercise")]
        self.assertEqual(numbers, ["8", "9"])

    def test_roundtrip(self):
        tree = self.build_tree()
        self.assertEqual(roundtrip(tree), tree)


if __name__ == "__main__":
    unittest.main()
