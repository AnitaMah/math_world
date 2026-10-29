from django.contrib.auth.models import User
from django.test import TestCase


class LessonPageTests(TestCase):
    """`/items/<id>/` у новому UI — теорія й вправи уроку (фаза 13)."""

    @classmethod
    def setUpTestData(cls):
        from education.models import (Answer, ContentBlock, Exercise, Grade, Item, Paragraph, Section,
                                      SubExercise, Subject, Textbook)
        math = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})[0]
        g5 = Grade.objects.create(subject=math, number=5, name_uk="5 клас")
        tb = Textbook.objects.create(subject=math, grade=g5, profile_code="m5", title="М5", pdf_sha256="b" * 64)
        s1 = Section.objects.create(grade=g5, number=1, name_uk="Розділ I. Натуральні числа")
        Paragraph.objects.create(section=s1, number=1, name_uk="§ 1. Натуральні числа")
        p2 = Paragraph.objects.create(section=s1, number=2, name_uk="§ 2. Додавання і віднімання")
        cls.item = Item.objects.create(paragraph=p2, number=7, content="7. Додавання натуральних чисел")
        ContentBlock.objects.create(item=cls.item, block_type="theory", order=1, text="Сума не змінюється.")
        block = ContentBlock.objects.create(item=cls.item, block_type="exercise", order=2)
        ex = Exercise.objects.create(textbook=tb, block=block, number=153, condition="Обчисли:", difficulty="high")
        sub = SubExercise.objects.create(exercise=ex, number="1", order=1, text="25 + 17")
        Answer.objects.create(exercise=ex, subexercise=sub, kind="book", text="42")

    def test_new_lesson_page(self):
        html = self.client.get(f"/items/{self.item.id}/").content.decode()
        self.assertIn("education/css/lesson.css", html)
        self.assertIn('class="page-lesson isl-2"', html)                # §2 → другий колір острова
        self.assertIn("Додавання натуральних чисел</h1>", html)          # без «7.» на початку
        self.assertIn(f'href="/grades/5/#lesson-{self.item.id}"', html)  # крихти й «На мапу»
        self.assertIn("Теорія", html)
        self.assertIn("Сума не змінюється.", html)
        self.assertIn("Вправи", html)
        self.assertIn('diff--high">Високий<', html)
        self.assertIn("25 + 17", html)

    def test_answers_only_for_staff(self):
        html = self.client.get(f"/items/{self.item.id}/").content.decode()
        self.assertNotIn("Відповідь (бачить лише вчитель)", html)
        self.assertNotIn(">1) 42", html)
        staff = User.objects.create_user("teacher", password="pw-12345678", is_staff=True)
        self.client.force_login(staff)
        html = self.client.get(f"/items/{self.item.id}/").content.decode()
        self.assertIn("Відповідь (бачить лише вчитель)", html)
        self.assertIn("1) 42", html)


    def test_block_filters(self):
        from education.templatetags.ui import block_icon, block_name, difficulty_name
        self.assertEqual(block_name("self_check"), "Перевір себе")       # без «(❓)» з моделі
        self.assertEqual(block_icon("wise_owl"), "owl")
        self.assertEqual(difficulty_name("olympiad"), "Олімпіадний")
        self.assertEqual(difficulty_name("unknown"), "")

    def test_german_cookie_falls_back_to_ukrainian_when_translation_missing(self):
        """FE-0642: *_de порожнє для цього уроку (0 з 75 параграфів перекладено) — запасний варіант uk."""
        self.client.cookies["mw_lang"] = "de"
        html = self.client.get(f"/items/{self.item.id}/").content.decode()
        self.assertIn("Додавання натуральних чисел</h1>", html)

    def test_german_cookie_uses_translation_when_present(self):
        self.item.content_de = "7. Addition natürlicher Zahlen"
        self.item.save()
        self.client.cookies["mw_lang"] = "de"
        html = self.client.get(f"/items/{self.item.id}/").content.decode()
        self.assertIn("Addition natürlicher Zahlen</h1>", html)

    def test_no_cookie_stays_ukrainian_even_with_translation_present(self):
        self.item.content_de = "7. Addition natürlicher Zahlen"
        self.item.save()
        html = self.client.get(f"/items/{self.item.id}/").content.decode()
        self.assertIn("Додавання натуральних чисел</h1>", html)
