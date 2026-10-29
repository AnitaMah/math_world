from django.contrib.auth.models import User
from django.test import TestCase


class ParagraphPageAndRedirectTests(TestCase):
    """Фаза 18: сторінка § замість старого списку пунктів; старі адреси — 301 на мапу."""

    @classmethod
    def setUpTestData(cls):
        from education.models import (ContentBlock, Exercise, Grade, Item, Paragraph, Section, SubExercise,
                                      Answer, Subject, Textbook)
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        cls.g5 = Grade.objects.create(subject=math, number=5, name_uk="5 клас")
        tb = Textbook.objects.create(subject=math, grade=cls.g5, profile_code="m5", title="М5", pdf_sha256="d" * 64)
        cls.s1 = Section.objects.create(grade=cls.g5, number=1, name_uk="Розділ I")
        cls.p1 = Paragraph.objects.create(section=cls.s1, number=1, name_uk="§ 1. Натуральні числа")
        cls.p2 = Paragraph.objects.create(section=cls.s1, number=2, name_uk="§ 2. Шкали")      # § як урок
        cls.i1 = Item.objects.create(paragraph=cls.p1, number=1, content="1. Ряд натуральних чисел")
        ContentBlock.objects.create(paragraph=cls.p1, block_type="summary", order=1, text="Головне: числа 1, 2, 3.")
        block = ContentBlock.objects.create(paragraph=cls.p2, block_type="exercise", order=1)
        ex = Exercise.objects.create(textbook=tb, block=block, number=50, condition="Обчисли:")
        sub = SubExercise.objects.create(exercise=ex, number="1", order=1, text="2 + 3")
        Answer.objects.create(exercise=ex, subexercise=sub, kind="book", text="5")
        Exercise.objects.create(textbook=tb, block=block, number=51, condition="Сумнівна умова", needs_review=True)

    def test_paragraph_overview_with_items(self):
        html = self.client.get(f"/paragraphs/{self.p1.id}/").content.decode()
        self.assertIn("Натуральні числа</h1>", html)
        self.assertIn("Уроки параграфа", html)
        self.assertIn(f'href="/items/{self.i1.id}/"', html)
        self.assertIn("Головне в параграфі", html)                       # блок рівня §
        self.assertIn("Головне: числа 1, 2, 3.", html)
        self.assertNotIn("Почати урок", html)                           # огляд, а не урок
        self.assertIn(f'href="/grades/5/#lesson-{self.i1.id}"', html)

    def test_paragraph_as_lesson(self):
        html = self.client.get(f"/paragraphs/{self.p2.id}/").content.decode()
        self.assertIn(f'href="/play/paragraph/{self.p2.id}/"', html)
        self.assertIn("Почати урок", html)
        self.assertIn(f'href="/grades/5/#lesson-p{self.p2.id}"', html)
        self.assertIn("2 + 3", html)
        self.assertNotIn("Сумнівна умова", html)                         # needs_review — лише персоналу
        staff = User.objects.create_user("t", password="pw-12345678", is_staff=True)
        self.client.force_login(staff)
        self.assertIn("Сумнівна умова", self.client.get(f"/paragraphs/{self.p2.id}/").content.decode())

    def test_item_crumbs_link_to_paragraph(self):
        html = self.client.get(f"/items/{self.i1.id}/").content.decode()
        self.assertIn(f'href="/paragraphs/{self.p1.id}/">§1 Натуральні числа</a>', html)

    def test_old_urls_redirect_permanently(self):
        cases = {
            "/grades/": "/",
            f"/grades/{self.g5.id}/sections/": "/grades/5/",
            f"/sections/{self.s1.id}/paragraphs/": f"/grades/5/#lesson-{self.i1.id}",
            f"/paragraphs/{self.p2.id}/items/": f"/paragraphs/{self.p2.id}/",
        }
        for old, new in cases.items():
            with self.subTest(old=old):
                resp = self.client.get(old)
                self.assertEqual(resp.status_code, 301)
                self.assertEqual(resp["Location"], new)
        self.assertEqual(self.client.get("/grades/999999/sections/").status_code, 404)

    def test_old_templates_and_static_are_gone(self):
        from pathlib import Path
        root = Path(__file__).parents[1]
        for rel in ["templates/education/item_list.html", "templates/education/item_detail.html",
                    "templates/education/grade_list.html", "templates/education/_map_partial.html",
                    "templates/education/play_v2.html", "templates/education/_lesson_blocks_v2.html",
                    "static/education/map.js", "static/education/map_data_uk.json",
                    "static/education/css/map_ui.css", "static/education/css/play-v2.css", "static/education/js/play-v2.js"]:
            self.assertFalse((root / rel).exists(), rel)
