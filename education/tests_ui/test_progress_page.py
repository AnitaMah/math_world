from django.test import TestCase


class ProgressPageTests(TestCase):
    """`/progress/` — зірки по параграфах і бали за тиждень (фаза 20, беклог FE-0630)."""

    @classmethod
    def setUpTestData(cls):
        from education.models import Grade, Subject, Textbook
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        g5 = Grade.objects.create(subject=math, number=5, name_uk="5 клас")
        Textbook.objects.create(subject=math, grade=g5, profile_code="m5", title="М5",
                                author="Мерзляк А. Г.", year=2018, pdf_sha256="e" * 64)
        Grade.objects.create(subject=math, number=6, name_uk="6 клас")

    def test_renders_grade_cards_and_chart(self):
        html = self.client.get("/progress/").content.decode()
        self.assertIn('data-grade="5"', html)
        self.assertIn('data-grade="6"', html)
        self.assertIn("Мерзляк, 2018", html)
        self.assertIn('data-me="history"', html)
        self.assertIn('id="tpl-progress-row"', html)
        self.assertIn("education/js/progress.js", html)

    def test_api_me_has_week_history(self):
        data = self.client.get("/api/me/").json()
        self.assertEqual(len(data["history"]), 7)
        self.assertEqual({tuple(sorted(d)) for d in data["history"]}, {("date", "points")})
        self.assertEqual(sum(d["points"] for d in data["history"]), 0)
