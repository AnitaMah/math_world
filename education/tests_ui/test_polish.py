from django.test import TestCase, override_settings


class PolishTests(TestCase):
    """Доступність і дрібниці (фаза 16)."""

    @classmethod
    def setUpTestData(cls):
        from education.models import Grade, Subject
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        Grade.objects.create(subject=math, number=5, name_uk="5 клас")

    def test_favicon_and_og(self):
        html = self.client.get("/").content.decode()
        self.assertIn('rel="icon" href="/static/education/img/favicon.svg"', html)
        self.assertIn('property="og:title"', html)
        self.assertIn('name="description"', html)

    def test_chips_have_text_labels(self):
        html = self.client.get("/").content.decode()
        for label in ("Зірки: ", "Бали: ", "Серія: "):
            self.assertIn(f'<span class="visually-hidden">{label}</span>', html)

    def test_map_text_alternative(self):
        html = self.client.get("/grades/5/").content.decode()
        self.assertIn('id="lessonList" aria-label="Усі уроки списком"', html)
        self.assertIn('aria-describedby="nodesHelp"', html)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
    def test_404_page(self):
        resp = self.client.get("/nema-takoi-storinky/")
        self.assertEqual(resp.status_code, 404)
        html = resp.content.decode()
        self.assertIn("Тут лише море", html)
        self.assertIn('href="/"', html)
        self.assertIn('lang="uk"', html)

    def test_500_is_static(self):
        from pathlib import Path
        html = (Path(__file__).parents[1] / "templates/500.html").read_text(encoding="utf-8")
        self.assertNotIn("{%", html)
        self.assertNotIn("{{", html)
        self.assertIn('lang="uk"', html)
        self.assertIn('href="/"', html)
