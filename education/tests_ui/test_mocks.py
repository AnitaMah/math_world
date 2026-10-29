from django.test import SimpleTestCase


class MockContractTests(SimpleTestCase):
    """Моки фронтенду = контракт із бекендом (фаза 6): tools/frontend/check_mocks.py."""

    def test_mocks_match_contract(self):
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[2] / "tools" / "frontend" / "check_mocks.py"
        spec = importlib.util.spec_from_file_location("check_mocks", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.check_all(), [])

    def test_checker_catches_broken_lesson(self):
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[2] / "tools" / "frontend" / "check_mocks.py"
        spec = importlib.util.spec_from_file_location("check_mocks", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        broken = {"grade": 5, "subject": "math", "textbook": None, "current": None, "sections": [
            {"id": 1, "number": 1, "title": "Р", "paragraphs": [{"id": 1, "number": 1, "title": "§", "items": [
                {"id": 1, "number": 1, "title": "У", "state": "done", "stars": 4, "solved": 0, "total": 0,
                 "tasks": {"auto": 0, "ai": 0}, "blocks": ["magic"], "map": {"x": None, "y": None}}]}]}]}
        errors = " | ".join(module.check_grade_map(broken, "test"))
        self.assertIn("stars поза 0–3", errors)
        self.assertIn("має бути `soon`", errors)
        self.assertIn("невідомі blocks", errors)
