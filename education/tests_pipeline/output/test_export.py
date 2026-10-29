"""Фаза 16: JSON-схема і експорт."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from education.pdf_pipeline.datatypes import BBox, Node, SourceRef
from education.pdf_pipeline.output.export import dumps, export_textbook, file_sha256, load_textbook, write_textbook
from education.pdf_pipeline.output.schema import SCHEMA_VERSION, SchemaError, validate_textbook
from education.pdf_pipeline.output.validate import Problem

SHA = "a" * 64
STAMP = "2026-10-07T12:00:00+00:00"


def src(page, y=100):
    return SourceRef(page, page, BBox(70, y, 700, y + 40), (1, 2))


def merzlyak_tree():
    """Мініатюра §1 Мерзляка: розділ → § → пункт → блоки → вправи → підпункти + рисунки."""
    root = Node("textbook", title="Математика. 5 клас",
                data={"profile": "math_merzlyak_5", "grade": 5, "subject": "math"})
    sec = root.add(Node("section", number="I", title="Натуральні числа і дії з ними", source=src(5), data={"index": 1}))
    par = sec.add(Node("paragraph", number="1", title="Натуральні числа", source=src(5),
                       data={"ocr_title": "9 1. НАТУРАЛЬНІ ЧИСЛА"}))
    item = par.add(Node("item", number="1", title="Ряд натуральних чисел", source=src(5)))
    theory = item.add(Node("block", text="Числа 1, 2, 3, … називають натуральними.", source=src(5),
                           data={"block_type": "theory", "line_keys": [[5, 3]]}))
    theory.add(Node("figure", number="1", title="Рис. 1", source=src(6, 300),
                    data={"figure_id": "p006_y300", "path": "figs/p006_y300.png"}))
    block = item.add(Node("block", source=src(7), data={"block_type": "exercise"}))
    ex = block.add(Node("exercise", number="12", text="Обчисліть:", source=src(7),
                        data={"difficulty": "medium", "condition": "Обчисліть:", "task_verb": "compute",
                              "answer_kind": "number", "is_word_problem": False, "auto_checkable": True,
                              "homework": True, "line_keys": [[7, 1]], "number_fixed": False,
                              "figure_refs": ["1"], "answer_book_parts": {"1": "673"}}))
    ex.add(Node("subexercise", number="1", text="238 + 435;",
                data={"raw_label": "1", "expr": "238 + 435", "expr_status": "ok", "answer": "673",
                      "answer_source": "computed", "answer_book": "673", "answer_verified": True}))
    bad = ex.add(Node("subexercise", number="2", text="98: 34;", needs_review=True,
                      data={"raw_label": "9", "ocr_fixed": True, "expr": "98 : 34", "expr_status": "suspect",
                            "expr_issues": ["implausible_result"]}))
    ex.add(Node("figure", number="1", source=src(6, 300), data={"figure_id": "p006_y300", "path": "figs/p006_y300.png"}))
    par.add(Node("block", text="Завдання № 1", source=src(40), data={"block_type": "self_test"}))
    return root, ex, bad


def export(root, **kw):
    return export_textbook(root, kw.pop("problems", ()), pdf_name="m5.pdf", pdf_sha256=SHA, created_at=STAMP, **kw)


class SchemaTests(unittest.TestCase):
    def test_export_passes_schema(self):
        data = export(merzlyak_tree()[0], pages=[7, 5, 6, 5])
        validate_textbook(data)
        self.assertEqual(data["schema_version"], SCHEMA_VERSION)
        self.assertEqual(data["meta"]["pages"], [5, 6, 7])

    def test_bad_data_rejected_with_path(self):
        data = export(merzlyak_tree()[0])
        broken = copy.deepcopy(data)
        broken["sections"][0]["paragraphs"][0]["items"][0]["blocks"][1]["type"] = "unknown_block"
        with self.assertRaisesRegex(SchemaError, "sections/0/paragraphs/0/items/0/blocks/1/type"):
            validate_textbook(broken)
        broken = copy.deepcopy(data)
        broken["meta"]["pdf_sha256"] = "xyz"
        with self.assertRaises(SchemaError):
            validate_textbook(broken)

    def test_unknown_field_rejected(self):
        data = export(merzlyak_tree()[0])
        data["sections"][0]["secret"] = 1
        with self.assertRaises(SchemaError):
            validate_textbook(data)


class ExportContentTests(unittest.TestCase):
    def setUp(self):
        self.data = export(merzlyak_tree()[0])
        item = self.data["sections"][0]["paragraphs"][0]["items"][0]
        self.theory, self.block = item["blocks"]
        self.ex = self.block["exercises"][0]

    def test_internal_fields_hidden(self):
        text = json.dumps(self.data)
        self.assertNotIn("line_keys", text)
        self.assertNotIn("line_ids", text)

    def test_exercise(self):
        self.assertEqual(self.ex["number"], "12")
        self.assertEqual(self.ex["difficulty"], "medium")
        self.assertTrue(self.ex["homework"])
        self.assertEqual(self.ex["figure_ids"], ["p006_y300"])
        self.assertEqual(self.ex["book_answer_parts"], {"1": "673"})
        self.assertEqual(self.ex["source"], {"pdf_page": 7, "book_page": 7, "bbox": [70, 100, 700, 140]})

    def test_subexercise_answers_and_flags(self):
        good, bad = self.ex["subexercises"]
        self.assertEqual(good["answer"], {"computed": "673", "book": "673", "verified": True})
        self.assertNotIn("raw_label", good)
        self.assertEqual((bad["raw_label"], bad["label_fixed"], bad["needs_review"]), ("9", True, True))
        self.assertNotIn("answer", bad)

    def test_figures_listed_once(self):
        self.assertEqual([f["id"] for f in self.data["figures"]], ["p006_y300"])
        self.assertEqual(self.theory["figure_ids"], ["p006_y300"])

    def test_paragraph_level_block(self):
        par = self.data["sections"][0]["paragraphs"][0]
        self.assertEqual([b["type"] for b in par["blocks"]], ["self_test"])
        self.assertEqual(par["ocr_title"], "9 1. НАТУРАЛЬНІ ЧИСЛА")

    def test_stats(self):
        s = self.data["stats"]
        self.assertEqual((s["exercises"], s["subexercises"], s["figures"], s["computed_answers"],
                          s["verified_answers"], s["blocks"]), (1, 2, 1, 1, 1, 3))

    def test_problems_exported(self):
        prob = Problem("expr_suspect", "info", "98 : 34", src(7), "п.1 / №12 / 2)")
        data = export(merzlyak_tree()[0], problems=[prob])
        self.assertEqual(data["problems"][0]["source"], {"pdf_page": 7, "book_page": 7, "bbox": [70, 100, 700, 140]})

    def test_misplaced_node_becomes_problem(self):
        root, ex, _ = merzlyak_tree()
        root.children[0].children[0].children[0].add(Node("exercise", number="99"))   # вправа прямо в пункті
        data = export(root)
        self.assertEqual([p["code"] for p in data["problems"]], ["export_skipped"])

    def test_vision_texts_kept(self):
        root, ex, bad = merzlyak_tree()
        ex.data.update(text_source="vision", ocr_text="OCR", vision_text="VISION", vision_status="applied")
        bad.data.update(text_source="vision", ocr_text="98: 34;")
        e = export(root)["sections"][0]["paragraphs"][0]["items"][0]["blocks"][1]["exercises"][0]
        self.assertEqual((e["text_source"], e["ocr_text"], e["vision_text"]), ("vision", "OCR", "VISION"))
        self.assertEqual(e["subexercises"][1]["ocr_text"], "98: 34;")


class DeterminismAndIoTests(unittest.TestCase):
    def test_two_runs_identical(self):
        a = dumps(export(merzlyak_tree()[0]))
        b = dumps(export(merzlyak_tree()[0]))
        self.assertEqual(a, b)

    def test_only_created_at_differs_by_default(self):
        a = export_textbook(merzlyak_tree()[0], pdf_name="m5.pdf", pdf_sha256=SHA)
        b = export_textbook(merzlyak_tree()[0], pdf_name="m5.pdf", pdf_sha256=SHA)
        a["meta"].pop("created_at"), b["meta"].pop("created_at")
        self.assertEqual(dumps(a), dumps(b))

    def test_write_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_textbook(export(merzlyak_tree()[0]), tmp)
            self.assertEqual(path, Path(tmp) / "math_merzlyak_5" / "textbook.json")
            text = path.read_text(encoding="utf-8")
            self.assertIn("Натуральні числа", text)                  # ensure_ascii=False
            self.assertEqual(load_textbook(path)["meta"]["profile"], "math_merzlyak_5")
            self.assertEqual(len(file_sha256(path)), 64)

    def test_load_wrong_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = export(merzlyak_tree()[0])
            data["schema_version"] = SCHEMA_VERSION + 1
            path = Path(tmp) / "t.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(SchemaError, "schema_version"):
                load_textbook(path)


if __name__ == "__main__":
    unittest.main()
