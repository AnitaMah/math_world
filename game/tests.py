"""Фаза 21Б: ігрова механіка — завдання уроку, бали, зірки, серія, ШІ-задачі, гість → акаунт."""
import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from education.ai_check import AiVerdict, FakeAiChecker, build_prompt, parse_verdict
from education.models import Answer, ContentBlock, Exercise, SubExercise
from education.tests.test_api import LessonFixture

from .models import Attempt, LessonProgress, Player
from .services import lesson_tasks, merge_players, record_answer, record_solution, stars_for


class GameFixture(LessonFixture):
    def setUp(self):
        super().setUp()
        # ще одна обчислювальна вправа «достатнього» рівня і одна текстова задача без відповіді
        self.ex2 = Exercise.objects.create(textbook=self.tb, block=self.ex.block, number=14, order=2,
                                           difficulty="sufficient", condition="Виконайте дії:", task_verb="compute")
        self.s21 = SubExercise.objects.create(exercise=self.ex2, number="1", order=0, text="43 + 24 · 58 − 39;",
                                              expr_status="ok")
        Answer.objects.create(exercise=self.ex2, subexercise=self.s21, kind="computed", text="1396")
        self.word = Exercise.objects.create(textbook=self.tb, block=self.ex.block, number=15, order=3,
                                            condition="У Петрика 5 яблук, у Олі на 3 більше. Скільки в Олі?",
                                            is_word_problem=True)
        self.player = Player.objects.create(session_key="s1")


class TasksTests(GameFixture):
    def test_tasks_order_kinds_points(self):
        tasks = lesson_tasks(self.item)
        self.assertEqual([(t.id[0], t.kind, t.points) for t in tasks],
                         [("s", "auto", 1), ("s", "auto", 2), ("e", "ai", 2)])
        self.assertEqual(tasks[0].sub, self.sub1)              # sub2 — needs_review, без відповіді
        self.assertNotIn(13, [t.exercise.number for t in tasks])   # вправа needs_review

    def test_ai_tasks_limited_to_three(self):
        for n in range(20, 25):
            Exercise.objects.create(textbook=self.tb, block=self.ex.block, number=n, order=n, is_word_problem=True)
        self.assertEqual(sum(t.kind == "ai" for t in lesson_tasks(self.item)), 3)

    def test_stars(self):
        self.assertEqual([stars_for(s, 10) for s in (0, 2, 3, 6, 7, 9, 10)], [0, 0, 1, 1, 2, 2, 3])
        self.assertEqual(stars_for(0, 0), 0)


class PointsTests(GameFixture):
    def test_points_once_and_progress(self):
        res = record_answer(self.player, self.s21, "1396")
        self.assertEqual((res.correct, res.points, res.progress.solved, res.progress.total), (True, 2, 1, 3))
        again = record_answer(self.player, self.s21, "1396")
        self.assertEqual((again.correct, again.points, again.already_solved), (True, 0, True))
        self.player.refresh_from_db()
        self.assertEqual(self.player.points, 2)

    def test_half_points_after_two_misses(self):
        record_answer(self.player, self.s21, "1")
        record_answer(self.player, self.s21, "2")
        self.assertEqual(record_answer(self.player, self.s21, "1 396").points, 1)

    def test_stars_grow_and_never_drop(self):
        record_answer(self.player, self.sub1, "673")
        prog = record_answer(self.player, self.s21, "1396").progress
        self.assertEqual((prog.solved, prog.stars), (2, 1))       # 2/3 = 67 % → ★
        Exercise.objects.create(textbook=self.tb, block=self.ex.block, number=30, order=30, is_word_problem=True)
        self.assertEqual(lesson_tasks(self.item, self.player)[-1].kind, "ai")
        from .services import recompute_progress
        self.assertEqual(recompute_progress(self.player, self.item).stars, 1)

    def test_streak(self):
        today = timezone.localdate()
        self.player.last_active, self.player.streak = today - timedelta(days=1), 4
        self.player.save()
        record_answer(self.player, self.sub1, "673")
        self.player.refresh_from_db()
        self.assertEqual(self.player.streak, 5)
        record_answer(self.player, self.s21, "1396")
        self.player.refresh_from_db()
        self.assertEqual(self.player.streak, 5)                    # той самий день
        self.player.last_active = today - timedelta(days=3)
        self.player.save()
        record_answer(self.player, self.s21, "1396")               # повтор — бали 0, серія не росте
        self.player.refresh_from_db()
        self.assertEqual(self.player.streak, 1)

    def test_manual_answer_has_priority(self):
        Answer.objects.create(exercise=self.ex2, subexercise=self.s21, kind="manual", text="1400")
        self.assertFalse(record_answer(self.player, self.s21, "1396").correct)
        self.assertTrue(record_answer(self.player, self.s21, "1400").correct)


class AiTests(GameFixture):
    def test_prompt_and_schema(self):
        prompt = build_prompt("Задача", "Розв'язок", 5, "8")
        self.assertIn("5 класу", prompt)
        self.assertIn("учневі не показуй): 8", prompt)
        self.assertEqual(parse_verdict({"verdict": "correct", "feedback": " Так "}), AiVerdict("correct", "Так"))
        from education.ai_check import AiUnavailable
        with self.assertRaises(AiUnavailable):
            parse_verdict({"verdict": "maybe", "feedback": ""})

    def test_record_solution(self):
        checker = FakeAiChecker(expect="8")
        res = record_solution(self.player, self.word, "5 + 3 = 7", checker)
        self.assertEqual((res.correct, res.verdict, res.points), (False, "incorrect", 0))
        res = record_solution(self.player, self.word, "5 + 3 = 8. Відповідь: 8 яблук", checker)
        self.assertEqual((res.correct, res.points), (True, 2))
        self.assertEqual(Attempt.objects.filter(kind="ai").count(), 2)
        self.assertIn("Скільки в Олі", checker.calls[0][0])


class ApiGameTests(GameFixture):
    def post(self, url, payload):
        return self.client.post(url, json.dumps(payload), content_type="application/json")

    def test_play_endpoint_without_answers(self):
        data = self.client.get(reverse("api_play_item", args=[self.item.pk])).json()
        self.assertEqual([t["kind"] for t in data["tasks"]], ["auto", "auto", "ai"])
        self.assertIsNone(data["progress"])
        body = json.dumps(data, ensure_ascii=False)
        for secret in ("673", "1396", "answer"):
            self.assertNotIn(f'"{secret}', body)

    def test_check_gives_points_and_progress(self):
        data = self.post(reverse("api_check", args=[self.s21.pk]), {"answer": "1396"}).json()
        self.assertEqual((data["correct"], data["points"], data["total_points"], data["streak"]), (True, 2, 2, 1))
        self.assertEqual(data["progress"], {"solved": 1, "total": 3, "points": 2, "stars": 1})
        play = self.client.get(reverse("api_play_item", args=[self.item.pk])).json()
        self.assertEqual([t["solved"] for t in play["tasks"]], [False, True, False])
        self.assertEqual(self.client.get(reverse("api_me")).json()["points"], 2)
        tree = self.client.get(reverse("api_grade_map", args=[5])).json()
        self.assertEqual(tree["sections"][0]["paragraphs"][0]["items"][0]["stars"], 1)

    def test_solution_endpoint(self):
        url = reverse("api_solution", args=[self.word.pk])
        with mock.patch("education.ai_check.get_ai_checker", return_value=None):
            self.assertEqual(self.post(url, {"solution": "8"}).json()["error"], "ai_unavailable")
        with mock.patch("education.ai_check.get_ai_checker", return_value=FakeAiChecker("8")):
            data = self.post(url, {"solution": "5+3=8"}).json()
        self.assertEqual((data["correct"], data["verdict"], data["points"]), (True, "correct", 2))
        not_ai = self.post(reverse("api_solution", args=[self.ex.pk]), {"solution": "x"})
        self.assertEqual((not_ai.status_code, not_ai.json()["error"]), (400, "not_ai_task"))

    def test_solution_network_error_is_503(self):
        broken = mock.Mock()
        broken.check.side_effect = RuntimeError("503 UNAVAILABLE")
        with mock.patch("education.ai_check.get_ai_checker", return_value=broken):
            resp = self.post(reverse("api_solution", args=[self.word.pk]), {"solution": "8"})
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(Attempt.objects.count(), 0)

    def test_play_page(self):
        resp = self.client.get(reverse("play_item", args=[self.item.pk]))
        self.assertContains(resp, reverse("api_play_item", args=[self.item.pk]))
        self.assertContains(resp, "play.js")
        self.assertContains(self.client.get(reverse("item_detail", args=[self.item.pk])), "Почати урок")


class GuestToAccountTests(GameFixture):
    def test_login_merges_guest_progress(self):
        self.client.post(reverse("api_check", args=[self.s21.pk]), json.dumps({"answer": "1396"}),
                         content_type="application/json")
        guest = Player.objects.get(user__isnull=True, points=2)
        user = User.objects.create_user("olia", password="pw-12345-long")
        account = Player.objects.create(user=user, points=10)
        LessonProgress.objects.create(player=account, item=self.item, stars=3, total=3, solved=3)
        self.client.post(reverse("login"), {"username": "olia", "password": "pw-12345-long"})
        account.refresh_from_db()
        self.assertFalse(Player.objects.filter(pk=guest.pk).exists())
        self.assertEqual(account.points, 12)
        self.assertEqual(account.attempts.count(), 1)
        self.assertEqual(account.progress.get(item=self.item).stars, 3)      # максимум, не сума

    def test_signup_keeps_guest_progress(self):
        self.client.post(reverse("api_check", args=[self.sub1.pk]), json.dumps({"answer": "673"}),
                         content_type="application/json")
        resp = self.client.post(reverse("signup"), {"username": "petryk", "password1": "Very-long-pass-77",
                                                    "password2": "Very-long-pass-77"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Player.objects.get(user__username="petryk").points, 1)

    def test_merge_players_direct(self):
        a, b = Player.objects.create(session_key="a", points=3), Player.objects.create(session_key="b", points=4)
        merge_players(a, b)
        b.refresh_from_db()
        self.assertEqual(b.points, 7)


class StatusMismatchTests(GameFixture):
    def test_mismatch_per_paragraph(self):
        SubExercise.objects.filter(pk=self.s21.pk).update(answer_check="mismatch")
        from io import StringIO
        out = StringIO()
        call_command("textbook_status", stdout=out)
        self.assertIn("розбіжності з відповідями книги: §1: 1", out.getvalue())
