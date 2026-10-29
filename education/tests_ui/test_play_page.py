from django.test import TestCase


class PlayPageTests(TestCase):
    """`/play/item|paragraph/<id>/` у новому UI — екран гри (фаза 14). Бекенд гри не змінюємо."""

    @classmethod
    def setUpTestData(cls):
        from education.models import (Answer, ContentBlock, Exercise, Grade, Item, Paragraph, Section,
                                      SubExercise, Subject, Textbook)
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        g5 = Grade.objects.create(subject=math, number=5, name_uk="5 клас")
        tb = Textbook.objects.create(subject=math, grade=g5, profile_code="m5", title="М5", pdf_sha256="c" * 64)
        s1 = Section.objects.create(grade=g5, number=1, name_uk="Розділ I")
        p1 = Paragraph.objects.create(section=s1, number=1, name_uk="§ 1. Натуральні числа")
        cls.p2 = Paragraph.objects.create(section=s1, number=2, name_uk="§ 2. Шкали")   # без пунктів → § як урок
        cls.i1 = Item.objects.create(paragraph=p1, number=1, content="1. Ряд натуральних чисел")
        cls.i2 = Item.objects.create(paragraph=p1, number=2, content="2. Цифри")        # без вправ

        def playable(**where):
            block = ContentBlock.objects.create(block_type="exercise", order=1, **where)
            ex = Exercise.objects.create(textbook=tb, block=block, number=10, condition="Обчисли:")
            sub = SubExercise.objects.create(exercise=ex, number="1", order=1, text="2 + 2")
            Answer.objects.create(exercise=ex, subexercise=sub, kind="book", text="4")

        playable(item=cls.i1)
        playable(paragraph=cls.p2)

    def test_new_play_page(self):
        html = self.client.get(f"/play/item/{self.i1.id}/").content.decode()
        self.assertIn("education/css/play.css", html)
        self.assertIn("education/js/play.js", html)
        self.assertIn('class="page-play isl-1"', html)
        self.assertNotIn('class="topbar', html)                       # повноекранна: без верхньої панелі
        self.assertNotIn('class="bottom-nav', html)
        self.assertIn(f'data-map="/grades/5/#lesson-{self.i1.id}"', html)
        self.assertIn('aria-label="Вийти з уроку"', html)
        self.assertIn("Урок 1 · Ряд натуральних чисел", html)
        self.assertIn(f'data-api="/api/play/items/{self.i1.id}/"', html)
        self.assertIn('id="soundToggle"', html)                           # беклог FE-0637
        self.assertIn('id="offlineBanner"', html)                         # беклог FE-0638
        # наступний урок з завданнями — § 2 (пункт 2 без вправ пропускаємо)
        self.assertIn(f'data-next="/play/paragraph/{self.p2.id}/"', html)

    def test_paragraph_lesson(self):
        html = self.client.get(f"/play/paragraph/{self.p2.id}/").content.decode()
        self.assertIn('class="page-play isl-2"', html)
        self.assertIn("§2 · Шкали", html)
        self.assertIn(f'data-map="/grades/5/#lesson-p{self.p2.id}"', html)
        self.assertIn('data-next=""', html)                            # останній урок класу


    def test_no_raw_colors_in_play_css(self):
        import re
        from pathlib import Path
        css = (Path(__file__).parents[1] / "static/education/css/play.css").read_text(encoding="utf-8")
        self.assertFalse(re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", css))
