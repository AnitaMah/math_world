"""Тести для education.pdf_pipeline.math_text — на реальних підпунктах з OCR Мерзляка."""
import unittest
from fractions import Fraction

import cv2
import numpy as np

from education.pdf_pipeline.datatypes import BBox, Node, SourceRef
from education.pdf_pipeline.math_text import (
    analyze_expression, check_tokens, detect_fraction_bars, enrich_math, format_answer, safe_eval, tokenize_expr,
)


class TokenizeTests(unittest.TestCase):
    def kinds(self, text):
        return [(t.kind, t.value) for t in tokenize_expr(text)]

    def test_basic(self):
        self.assertEqual(self.kinds("(43 + 24) · 58 − 39"), [
            ("lparen", "("), ("number", "43"), ("op", "+"), ("number", "24"), ("rparen", ")"),
            ("op", "*"), ("number", "58"), ("op", "-"), ("number", "39")])

    def test_division_and_decimal(self):
        self.assertEqual(self.kinds("3,5 : 7"), [("number", "3.5"), ("op", "/"), ("number", "7")])

    def test_thousands(self):
        toks = tokenize_expr("2 000 − 546")
        self.assertEqual(toks[0].value, "2000")
        self.assertEqual(toks[0].suspect, "grouped_number")

    def test_suspects(self):
        suspects = {t.raw: t.suspect for t in tokenize_expr("98 - 34 + 12°5 + 82). 6") if t.suspect}
        self.assertEqual(suspects, {"-": "hyphen_operator", "°": "degree_as_mul", ".": "dot_as_mul"})

    def test_words_and_vars(self):
        kinds = [t.kind for t in tokenize_expr("від 45 число 19")]
        self.assertIn("word", kinds)
        self.assertEqual(tokenize_expr("a + 5")[0].kind, "var")


class CheckTokensTests(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(check_tokens(tokenize_expr("(43 + 24) · (58 − 39)")), [])

    def test_problems(self):
        self.assertIn("double_operator", check_tokens(tokenize_expr("43 −− 24")))
        self.assertIn("missing_operator", check_tokens(tokenize_expr("12 : 5 − 4 1")))
        self.assertIn("bad_parentheses", check_tokens(tokenize_expr("(43 + 24")))
        self.assertIn("bad_parentheses", check_tokens(tokenize_expr("43 + 24)")))
        self.assertIn("dangling_operator", check_tokens(tokenize_expr("43 +")))


class SafeEvalTests(unittest.TestCase):
    def test_precedence_and_parentheses(self):
        self.assertEqual(safe_eval("43 + 24 · 58 − 39"), 1396)
        self.assertEqual(safe_eval("(43 + 24) · 58 − 39"), 3847)
        self.assertEqual(safe_eval("43 + 24 · (58 − 39)"), 499)
        self.assertEqual(safe_eval("(43 + 24) · (58 − 39)"), 1273)

    def test_exact_fractions(self):
        self.assertEqual(safe_eval("1 : 3 + 1 : 3 + 1 : 3"), 1)
        self.assertEqual(safe_eval("7 : 2"), Fraction(7, 2))

    def test_errors(self):
        for bad in ["5 : 0", "__import__('os')", "2 ** 10", "abs(5)", ""]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                safe_eval(bad)

    def test_format(self):
        self.assertEqual(format_answer(Fraction(17)), "17")
        self.assertEqual(format_answer(Fraction(7, 2)), "7/2")
        self.assertEqual(format_answer(Fraction(-3)), "−3")


class AnalyzeTests(unittest.TestCase):
    def test_real_ocr_subitems(self):
        cases = {
            "238 + 435;": ("ok", "673"),
            "843 − 457;": ("ok", "386"),
            "3596 − 3596 : (2314 − 2256).": ("ok", "3534"),
            "(488 + 808): 18.": ("ok", "72"),
            "23 - 46;": ("suspect", None),          # «-» замість «·» → ще й від'ємна відповідь
            "98: 34;": ("suspect", None),           # «:» замість «·» → дробова відповідь
            "36:9+18°5;": ("suspect", None),         # «°» замість «·»
            "12:5-4 1;": ("malformed", None),
            "6 і 24;": ("not_expression", None),
            "від 45 число 19.": ("not_expression", None),
            "x + 5": ("not_expression", None),
        }
        for text, (status, answer) in cases.items():
            with self.subTest(text=text):
                r = analyze_expression(text)
                self.assertEqual((r.status, r.answer), (status, answer))

    def test_pretty_expression(self):
        self.assertEqual(analyze_expression("(43+24)·58−39;").expression, "(43 + 24) · 58 − 39")

    def test_fractional_answer_allowed_for_older_grades(self):
        r = analyze_expression("7 : 2", natural_numbers=False)
        self.assertEqual((r.status, r.answer), ("ok", "7/2"))


def draw_fraction(img, x, y):
    """Малює «1 над рискою 6» з центром риски в (x, y)."""
    cv2.putText(img, "1", (x - 4, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1)
    cv2.line(img, (x - 8, y), (x + 8, y), 0, 1)
    cv2.putText(img, "6", (x - 4, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1)


class FractionBarTests(unittest.TestCase):
    def test_fraction_found_minus_and_letters_ignored(self):
        img = np.full((600, 400), 255, np.uint8)
        draw_fraction(img, 200, 300)
        cv2.line(img, (60, 300), (76, 300), 0, 1)                         # мінус: над і під порожньо
        cv2.putText(img, "57 = 3", (250, 400), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1)   # «5», «7», «=»
        bars = detect_fraction_bars(img, text_height=18)
        self.assertEqual(len(bars), 1)
        self.assertTrue(bars[0].x0 <= 200 <= bars[0].x1)

    def test_header_ignored(self):
        img = np.full((600, 400), 255, np.uint8)
        draw_fraction(img, 200, 30)                                       # у смузі колонтитула
        self.assertEqual(detect_fraction_bars(img, text_height=18), [])


class EnrichMathTests(unittest.TestCase):
    def build(self):
        root = Node("textbook")
        ex = root.add(Node("block", data={"block_type": "exercise"})).add(
            Node("exercise", number="12", source=SourceRef(7, bbox=BBox(70, 100, 700, 200)),
                 data={"task_verb": "compute"}))
        ex.add(Node("subexercise", number="1", text="238 + 435;"))
        ex.add(Node("subexercise", number="2", text="23 - 46;"))
        other = root.children[0].add(Node("exercise", number="13", data={"task_verb": "name"}))
        other.add(Node("subexercise", number="1", text="2 + 2"))
        return root

    def test_answers_and_flags(self):
        root = self.build()
        stats = enrich_math(root)
        sub1, sub2, other = root.find("subexercise")
        self.assertEqual((sub1.data["answer"], sub1.data["answer_source"]), ("673", "computed"))
        self.assertNotIn("answer", sub2.data)
        self.assertTrue(sub2.needs_review)
        self.assertNotIn("expr", other.data)          # не обчислювальна вправа — не чіпаємо
        self.assertEqual((stats.expressions, stats.ok, stats.suspect), (2, 1, 1))

    def test_fraction_marks_exercise(self):
        root = self.build()
        enrich_math(root, fraction_bars={7: [BBox(300, 120, 320, 160)]})
        self.assertTrue(root.find("exercise")[0].data["has_fractions"])
        self.assertTrue(root.find("exercise")[0].needs_review)


if __name__ == "__main__":
    unittest.main()


class PowerTests(unittest.TestCase):
    def test_superscript_power(self):
        r = analyze_expression("26² – (12² · 3 + 175);", trusted_text=True)
        self.assertEqual((r.status, r.answer, r.expression), ("ok", "69", "26² − (12² · 3 + 175)"))

    def test_power_of_bracket_and_chain(self):
        self.assertEqual(analyze_expression("(2 + 3)² + 4³").answer, "89")
        self.assertEqual(analyze_expression("2 · 3¹⁰").answer, "118098")

    def test_stray_superscript_is_malformed(self):
        self.assertEqual(analyze_expression("5 + ² · 3").status, "malformed")

    def test_huge_exponent_rejected(self):
        self.assertEqual(analyze_expression("2 + 3⁹⁹").status, "malformed")


class GroupedNumberTrustTests(unittest.TestCase):
    def test_ocr_text_with_spaces_is_suspect(self):
        r = analyze_expression("67 216 : 8;")
        self.assertEqual((r.status, r.issues), ("suspect", ["grouped_number"]))

    def test_text_layer_with_spaces_is_ok(self):
        r = analyze_expression("67 216 : 8;", trusted_text=True)
        self.assertEqual((r.status, r.answer, r.expression), ("ok", "8402", "67216 : 8"))
        r = analyze_expression("(318 . 207 − 64 934) . 276 + 604 . 88;", trusted_text=True)
        self.assertEqual((r.status, r.answer), ("ok", "299344"))
