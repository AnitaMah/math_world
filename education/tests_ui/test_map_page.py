from django.test import TestCase


class GradeMapPageTests(TestCase):
    """`/grades/<n>/` — сторінка мапи (фаза 8)."""

    @classmethod
    def setUpTestData(cls):
        from education.models import Grade, Subject
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        Grade.objects.create(subject=math, number=5, name_uk="5 клас")

    def test_page_renders_map_shell(self):
        response = self.client.get("/grades/5/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-grade="5"', html)
        self.assertIn("education/js/map.js", html)
        self.assertIn("education/css/map.css", html)
        self.assertIn("<title>Мапа 5 класу · Математичний світ</title>", html)
        for state in ("mapLoading", "mapError", "mapEmpty", "lessonPanel", "mapNodes", "tpl-lesson-panel", "tpl-island-row"):
            self.assertIn(f'id="{state}"', html)
        # панель підписується на події мапи раніше, ніж мапа їх надсилає
        self.assertLess(html.index("js/lesson-panel.js"), html.index("js/map.js"))

    def test_grade_tab_active_and_links_to_maps(self):
        html = self.client.get("/grades/5/").content.decode()
        self.assertIn('href="/grades/5/" aria-current="page"', html)

    def test_unknown_grade_404(self):
        self.assertEqual(self.client.get("/grades/99/").status_code, 404)

    def test_old_sections_url_still_works(self):
        # старі сторінки живуть до фази 18; /grades/<id>/sections/ не конфліктує з /grades/<n>/
        from django.urls import resolve
        self.assertEqual(resolve("/grades/3/sections/").url_name, "section_list")
        self.assertEqual(resolve("/grades/5/").url_name, "grade_map_page")
