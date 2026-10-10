"""Фаза 15: vision-LLM корекція — лише з FakeVisionClient (без мережі)."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from education.pdf_pipeline.datatypes import BBox, Node, SourceRef
from education.pdf_pipeline.vision import (
    CachedClient, DailyBudget, FakeVisionClient, VisionBudgetExceeded, cache_key, call_with_backoff,
    estimate_tokens, exercise_ocr_text, judge, run_vision, select_targets, validate_response,
)

PAGE = np.full((400, 700, 3), 255, np.uint8)


def ex3_tree():
    """Вправа 3 зі стор. 9 Мерзляка так, як її прочитав OCR."""
    root = Node("textbook")
    block = root.add(Node("block", data={"block_type": "exercise"}))
    ex = block.add(Node("exercise", number="3", source=SourceRef(9, bbox=BBox(20, 20, 600, 90)),
                        data={"condition": "Обчисліть:", "task_verb": "compute"}))
    for n, text, status in [("1", "12:5-4 1;", "malformed"), ("2", "12°5-1;", "malformed"), ("3", "12°(5+1);", "malformed")]:
        sub = ex.add(Node("subexercise", number=n, text=text, data={"expr_status": status}))
        sub.needs_review = True
    ex.needs_review = True
    ok = block.add(Node("exercise", number="4", text="Назвіть п'ять чисел", source=SourceRef(9, bbox=BBox(20, 100, 600, 130))))
    return root, ex, ok


GOOD = {"text": "Обчисліть:", "confidence": 0.95,
        "subitems": [{"n": "1", "text": "12 · 5 + 1;"}, {"n": "2", "text": "12 · 5 − 1;"}, {"n": "3", "text": "12 · (5 + 1);"}]}


class ClientInfraTests(unittest.TestCase):
    def test_backoff_retries_429_then_succeeds(self):
        calls, sleeps = [], []

        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
            return "ok"
        self.assertEqual(call_with_backoff(fn, sleep=sleeps.append), "ok")
        self.assertEqual(sleeps, [5.0, 10.0])

    def test_backoff_other_errors_not_retried(self):
        sleeps = []
        with self.assertRaises(ValueError):
            call_with_backoff(lambda: (_ for _ in ()).throw(ValueError("400 bad")), sleep=sleeps.append)
        self.assertEqual(sleeps, [])

    def test_budget_resets_next_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            day = ["2026-10-07"]
            budget = DailyBudget(Path(tmp) / "b.json", limit=1, today=lambda: day[0])
            budget.spend()
            with self.assertRaises(VisionBudgetExceeded):
                budget.spend()
            day[0] = "2026-10-08"
            budget.spend()
            self.assertEqual(budget.used, 1)

    def test_cache_key_depends_on_image_prompt_model(self):
        base = cache_key(b"png", "prompt v1", "m", {})
        self.assertNotEqual(base, cache_key(b"png2", "prompt v1", "m", {}))
        self.assertNotEqual(base, cache_key(b"png", "prompt v2", "m", {}))
        self.assertNotEqual(base, cache_key(b"png", "prompt v1", "m2", {}))

    def test_cached_client_spends_budget_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeVisionClient([GOOD])
            client = CachedClient(fake, Path(tmp) / "c", DailyBudget(Path(tmp) / "b.json", limit=5))
            client.transcribe(b"x", "p", {})
            self.assertFalse(client.last_from_cache)
            self.assertEqual(client.transcribe(b"x", "p", {}), GOOD)
            self.assertTrue(client.last_from_cache)
            self.assertEqual((len(fake.calls), client.budget.used), (1, 1))

    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens(300, 200), 258)
        self.assertEqual(estimate_tokens(1000, 300), 258 * 2)


class SelectAndJudgeTests(unittest.TestCase):
    def test_select_targets(self):
        root, ex, ok = ex3_tree()
        targets = select_targets(root)
        self.assertEqual([t.exercise.number for t in targets], ["3"])
        self.assertEqual(targets[0].reasons, ["expr_malformed", "needs_review"])

    def test_fraction_first(self):
        root, ex, ok = ex3_tree()
        ok.data["has_fractions"] = True
        self.assertEqual([t.exercise.number for t in select_targets(root)], ["4", "3"])

    def test_ocr_text(self):
        _, ex, _ = ex3_tree()
        self.assertEqual(exercise_ocr_text(ex), "Обчисліть:\n1) 12:5-4 1;\n2) 12°5-1;\n3) 12°(5+1);")

    def test_schema(self):
        self.assertIsNone(validate_response(GOOD))
        self.assertIsNotNone(validate_response({"text": "x"}))
        self.assertIsNotNone(validate_response({**GOOD, "confidence": 3}))

    def test_judge(self):
        _, ex, _ = ex3_tree()
        ocr = exercise_ocr_text(ex)
        self.assertEqual(judge(ocr, GOOD, ["1", "2", "3"]).status, "applied")
        self.assertEqual(judge(ocr, {**GOOD, "text": "Обчисліть: " + "дуже довгий вигаданий текст " * 10},
                               ["1", "2", "3"]).status, "rejected_length")
        self.assertEqual(judge(ocr, {"text": "Зовсім інша задача про яблука", "subitems": [], "confidence": 1},
                               ["1", "2", "3"]).status, "rejected_cer")
        self.assertEqual(judge(ocr, {**GOOD, "subitems": GOOD["subitems"][:2]}, ["1", "2", "3"]).status, "applied_review")
        self.assertEqual(judge(ocr, "не JSON", []).status, "invalid")


class RunVisionTests(unittest.TestCase):
    def test_applied_and_recomputed(self):
        root, ex, _ = ex3_tree()
        stats = run_vision(root, {9: PAGE}, FakeVisionClient([GOOD]))
        self.assertEqual(stats.by_status, {"applied": 1})
        self.assertEqual(ex.data["text_source"], "vision")
        self.assertEqual(ex.data["ocr_text"].splitlines()[1], "1) 12:5-4 1;")      # OCR-версія збережена
        subs = ex.children
        self.assertEqual(subs[0].text, "12 · 5 + 1;")
        self.assertEqual(subs[0].data["ocr_text"], "12:5-4 1;")
        self.assertEqual([s.data.get("answer") for s in subs], ["61", "59", "72"])  # перераховано
        self.assertFalse(ex.needs_review)

    def test_typographic_apostrophe_is_canonical(self):
        root, ex, _ = ex3_tree()
        good = {**GOOD, "text": "Знайдіть від\u2019ємник:"}
        run_vision(root, {9: PAGE}, FakeVisionClient([good]))
        self.assertEqual(ex.data["condition"], "Знайдіть від'ємник:")

    def test_rejected_keeps_ocr_and_review(self):
        root, ex, _ = ex3_tree()
        run_vision(root, {9: PAGE}, FakeVisionClient([{"text": "Про яблука і груші в саду", "subitems": [], "confidence": 0.9}]))
        self.assertEqual(ex.data["vision_status"], "rejected_cer")
        self.assertEqual(ex.data["text_source"], "ocr")
        self.assertEqual(ex.children[0].text, "12:5-4 1;")
        self.assertIn("vision_text", ex.data)                                    # у звіт
        self.assertTrue(ex.needs_review)

    def test_dry_run_sends_nothing(self):
        root, ex, _ = ex3_tree()
        fake = FakeVisionClient([GOOD])
        stats = run_vision(root, {9: PAGE}, fake, dry_run=True)
        self.assertEqual((len(fake.calls), stats.selected, len(stats.planned)), (0, 1, 1))
        self.assertGreater(stats.estimated_tokens, 0)
        self.assertNotIn("vision_status", ex.data)

    def test_limit(self):
        root, ex, ok = ex3_tree()
        ok.needs_review = True
        fake = FakeVisionClient([GOOD])
        stats = run_vision(root, {9: PAGE}, fake, limit=1)
        self.assertEqual((stats.candidates, stats.selected, len(fake.calls)), (2, 1, 1))

    def test_budget_exhausted_mid_run(self):
        root, ex, ok = ex3_tree()
        ok.needs_review = True
        with tempfile.TemporaryDirectory() as tmp:
            client = CachedClient(FakeVisionClient([GOOD]), Path(tmp) / "c", DailyBudget(Path(tmp) / "b.json", limit=1))
            stats = run_vision(root, {9: PAGE}, client)
        self.assertTrue(stats.budget_stopped)
        self.assertEqual(stats.sent, 1)
        self.assertNotIn("vision_status", ok.data)                               # друга вправа не чіпана

    def test_network_error_does_not_stop_run(self):
        root, ex, ok = ex3_tree()
        ok.needs_review = True
        stats = run_vision(root, {9: PAGE}, FakeVisionClient([RuntimeError("500 boom"), GOOD]))
        self.assertEqual(stats.errors, 1)
        self.assertEqual(ex.data["vision_status"], "error")
        self.assertIn("vision_status", ok.data)

    def test_prompt_contains_ocr_hint(self):
        root, ex, _ = ex3_tree()
        fake = FakeVisionClient([GOOD])
        run_vision(root, {9: PAGE}, fake)
        self.assertIn("12:5-4 1;", fake.calls[0][1])
        self.assertTrue(fake.calls[0][0].startswith(b"\x89PNG"))

    def test_json_roundtrip_after_vision(self):
        root, ex, _ = ex3_tree()
        run_vision(root, {9: PAGE}, FakeVisionClient([GOOD]))
        self.assertEqual(Node.from_dict(json.loads(json.dumps(root.to_dict()))).to_dict(), root.to_dict())


if __name__ == "__main__":
    unittest.main()


class VisionEnvTests(unittest.TestCase):
    def test_key_is_read_from_env_file_and_real_env_wins(self):
        import os
        from unittest import mock
        from education.pdf_pipeline.vision import vision_env
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("GEMINI_API_KEY=from-file\nGEMINI_MODEL='m-1'\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("GEMINI_API_KEY", None)
                self.assertEqual(vision_env(env_file)["GEMINI_API_KEY"], "from-file")
                self.assertEqual(vision_env(env_file)["GEMINI_MODEL"], "m-1")
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "from-env"}):
                self.assertEqual(vision_env(env_file)["GEMINI_API_KEY"], "from-env")
