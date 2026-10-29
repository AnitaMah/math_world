from django.template import engines
from django.test import SimpleTestCase


class ComponentIncludeTests(SimpleTestCase):
    """_stars.html і _progress.html (фаза 4)."""

    def render(self, src, ctx=None):
        return engines["django"].from_string(src).render(ctx or {})

    def test_stars_two_of_three(self):
        html = self.render('{% include "education/_stars.html" with count=2 size=20 %}')
        self.assertEqual(html.count("star--on"), 2)
        self.assertEqual(html.count("star--off"), 1)
        self.assertIn('aria-label="2 з 3 зірок"', html)
        self.assertIn('width="20"', html)

    def test_stars_defaults_and_outline(self):
        html = self.render('{% include "education/_stars.html" with outline=True %}')
        self.assertEqual(html.count("star--off"), 3)
        self.assertIn("stars--outline", html)
        self.assertIn('width="14"', html)
        self.assertIn('aria-label="0 з 3 зірок"', html)

    def test_stars_from_variable(self):
        html = self.render('{% include "education/_stars.html" with count=lesson.stars %}', {"lesson": {"stars": 3}})
        self.assertEqual(html.count("star--on"), 3)

    def test_progress_percent_and_aria(self):
        html = self.render('{% include "education/_progress.html" with value=6 max=17 label="Розв’язано 6 з 17" size="md" %}')
        self.assertIn("--p: 35%", html)  # 6/17 = 35.3 %
        self.assertIn('role="progressbar"', html)
        self.assertIn('aria-valuenow="6"', html)
        self.assertIn('aria-valuemax="17"', html)
        self.assertIn("progress--md", html)

    def test_progress_empty_lesson(self):
        html = self.render('{% include "education/_progress.html" with value=0 max=0 %}')
        self.assertIn("--p: 0%", html)
