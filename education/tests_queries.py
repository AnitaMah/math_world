"""0874: N+1. Кількість SQL-запитів не росте з кількістю вправ/підпунктів у уроці (assertNumQueries)."""
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from education.models import Answer, ContentBlock, Exercise, Figure, SubExercise
from game.tests import GameFixture


class QueryCountTests(GameFixture):
    """Міряємо запити для уроку з N вправами, додаємо ще 6 вправ (з підпунктами, відповідями, рисунками) — має бути стільки ж."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user("staff", password="x", is_staff=True)
        self.n = 100

    def grow(self, count=6, needs_review=False):
        block = ContentBlock.objects.filter(item=self.item, block_type="exercise").first()
        for _ in range(count):
            self.n += 1
            ex = Exercise.objects.create(textbook=self.tb, block=block, number=self.n, order=self.n, difficulty="medium",
                                         condition="Обчисліть:", task_verb="compute", needs_review=needs_review,
                                         source_page=7)
            fig = Figure.objects.create(textbook=self.tb, figure_id=f"f{self.n}", source_page=7)
            ex.figures.add(fig)
            for k in (1, 2):
                sub = SubExercise.objects.create(exercise=ex, number=str(k), order=k, text=f"{k} + {self.n}",
                                                 expr_status="ok", needs_review=needs_review)
                Answer.objects.create(exercise=ex, subexercise=sub, kind="book", text=str(k + self.n))

    def count(self, url):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        self.last_body = response.content.decode("utf-8")
        return len(ctx)

    def assert_flat(self, url, needs_review=False, login=None, shows_exercises=True):
        if login:
            self.client.force_login(login)
        self.grow(2, needs_review)
        before = self.count(url)
        self.grow(6, needs_review)
        after = self.count(url)
        # страшилка проти порожнього тесту: сторінка справді показує щойно додані вправи
        if shows_exercises:
            self.assertIn(f"{self.n}", self.last_body, f"{url}: нові вправи не потрапили на сторінку")
        self.assertEqual(before, after, f"{url}: {before} → {after} запитів після +6 вправ (N+1?)")

    # --- гра і публічні сторінки
    def test_item_page(self):
        self.assert_flat(reverse("item_detail", args=[self.item.pk]))

    def test_play_page(self):
        self.assert_flat(reverse("play_item", args=[self.item.pk]), shows_exercises=False)    # оболонка, вправи тягне API

    def test_api_play(self):
        self.assert_flat(reverse("api_play_item", args=[self.item.pk]))

    def test_api_exercise_list(self):
        self.assert_flat(reverse("api_item_exercises", args=[self.item.pk]) + "?page_size=100")

    def test_api_lesson_detail(self):
        self.assert_flat(reverse("api_item", args=[self.item.pk]), shows_exercises=False)     # лише теорія

    def test_api_textbook_tree(self):
        self.assert_flat(reverse("api_textbook_tree", args=[self.tb.pk]), shows_exercises=False)   # лише лічильники

    # --- сторінка перевірки (персонал); у черзі needs_review
    def test_review_index(self):
        self.assert_flat(reverse("review_index"), needs_review=True, login=self.staff)

    def test_review_detail_exercise(self):
        self.grow(1, needs_review=True)
        ex = Exercise.objects.filter(needs_review=True).first()
        url = reverse("review_detail", args=["exercise", ex.pk])
        self.client.force_login(self.staff)
        before = self.count(url)
        self.grow(6, needs_review=True)
        self.assertEqual(before, self.count(url))
