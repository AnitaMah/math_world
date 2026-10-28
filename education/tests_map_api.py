"""Бекенд під дизайн мапи-архіпелагу: стани уроків «по черзі», /api/grades/, /api/grades/<n>/map/, /me/, /play/."""
from django.contrib.auth.models import User
from django.test import SimpleTestCase
from django.urls import reverse

from education.game import record_answer
from education.grade_map import assign_states, load_grade
from education.models import Answer, ContentBlock, Exercise, Item, SubExercise
from education.tests_game import GameFixture
from tools.frontend.check_mocks import STATES, check_grade_map


class AssignStatesTests(SimpleTestCase):
    def test_new_player_first_lesson_is_current(self):
        self.assertEqual(assign_states([(5, 0), (5, 0), (0, 0), (5, 0)]),
                         (["current", "locked", "soon", "locked"], 0))

    def test_star_opens_next_and_soon_does_not_block(self):
        self.assertEqual(assign_states([(5, 2), (0, 0), (0, 0), (5, 0), (5, 0)]),
                         (["done", "soon", "soon", "current", "locked"], 3))

    def test_earlier_open_is_not_closed(self):
        # зірки в уроці 2 (наприклад, після злиття гостя) — урок 1 лишається поточним, урок 3 відкритий
        states, cur = assign_states([(5, 0), (5, 3), (5, 0), (5, 0)])
        self.assertEqual((states, cur), (["current", "done", "open", "locked"], 0))

    def test_all_done_has_no_current(self):
        self.assertEqual(assign_states([(3, 1), (3, 3)]), (["done", "done"], None))

    def test_empty(self):
        self.assertEqual(assign_states([]), ([], None))


class MapFixture(GameFixture):
    def setUp(self):
        super().setUp()
        # урок 2 з одним авто-завданням і урок 3 без вправ («у хмарах»)
        self.item2 = Item.objects.create(paragraph=self.par, number=2, content="Цифри. Десятковий запис\nтекст")
        block = ContentBlock.objects.create(item=self.item2, block_type="exercise", order=1)
        ex = Exercise.objects.create(textbook=self.tb, block=block, number=30, order=0, difficulty="medium",
                                     condition="Обчисліть:")
        sub = SubExercise.objects.create(exercise=ex, number="1", order=0, text="2 + 2", expr_status="ok")
        Answer.objects.create(exercise=ex, subexercise=sub, kind="book", text="4")
        self.item3 = Item.objects.create(paragraph=self.par, number=3, content="Площина")

    def bind_client_to_player(self):
        """Клієнт тесту = гравець фікстури (анонім за ключем сесії)."""
        session = self.client.session
        session.save()
        self.player.session_key = session.session_key
        self.player.save()

    def map(self):
        return self.client.get(reverse("api_grade_map", args=[5])).json()

    def lessons(self, data=None):
        return (data or self.map())["sections"][0]["paragraphs"][0]["items"]


class GradeMapContractTests(MapFixture):
    def test_matches_frontend_contract(self):
        self.assertEqual(check_grade_map(self.map(), "api"), [])

    def test_guest_states_and_fields(self):
        data = self.map()
        l1, l2, l3 = self.lessons(data)
        self.assertEqual([l["state"] for l in (l1, l2, l3)], ["current", "locked", "soon"])
        self.assertEqual(data["current"], {"kind": "item", "id": self.item.pk})
        self.assertEqual((l1["tasks"], l1["total"], l1["solved"], l1["stars"]), ({"auto": 2, "ai": 1}, 3, 0, 0))
        self.assertEqual(l1["blocks"], ["theory", "exercise"])
        self.assertEqual(l2["title"], "Цифри. Десятковий запис")
        self.assertEqual(l3["tasks"], {"auto": 0, "ai": 0})
        self.assertEqual(l1["map"], {"x": None, "y": None})
        self.assertEqual(data["textbook"], {"author": self.tb.author, "year": self.tb.year})
        par = data["sections"][0]["paragraphs"][0]
        self.assertEqual(set(par), {"id", "number", "title", "items"})

    def test_manual_map_position(self):
        Item.objects.filter(pk=self.item.pk).update(map_x=100, map_y=200)
        self.assertEqual(self.lessons()[0]["map"], {"x": 100, "y": 200})

    def test_progress_opens_next_lesson(self):
        self.bind_client_to_player()
        record_answer(self.player, self.s21, "1396")        # 1 з 3 завдань → 1 зірка
        data = self.map()
        l1, l2, l3 = self.lessons(data)
        self.assertEqual((l1["state"], l1["stars"], l1["solved"]), ("done", 1, 1))
        self.assertEqual((l2["state"], data["current"]["id"]), ("current", self.item2.pk))
        self.assertEqual(l3["state"], "soon")

    def test_paragraph_without_items_is_the_lesson(self):
        """Тарасенкова: урок = параграф, поля уроку на параграфі, items порожній."""
        self.item.delete(); self.item2.delete(); self.item3.delete()
        ContentBlock.objects.create(paragraph=self.par, block_type="self_test", order=1)
        data = self.map()
        par = data["sections"][0]["paragraphs"][0]
        self.assertEqual((par["items"], par["state"], par["id"]), ([], "soon", self.par.pk))
        self.assertEqual(par["blocks"], ["self_check"])
        self.assertEqual(check_grade_map(data, "api6"), [])

    def test_states_are_known(self):
        self.assertTrue({l["state"] for l in self.lessons()} <= STATES)

    def test_query_count_does_not_grow_with_lessons(self):
        with self.assertNumQueries(self.queries_for_map()):
            self.map()
        for n in range(10, 20):
            Item.objects.create(paragraph=self.par, number=n, content=f"Урок {n}")
        with self.assertNumQueries(self.queries_for_map()):
            self.map()

    def queries_for_map(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            self.map()
        return len(ctx)


class GradeMapLangTests(MapFixture):
    """FE-0642: заголовки на мапі мовою cookie `mw_lang`, запасний варіант uk де `*_de` порожнє."""

    def test_default_is_ukrainian(self):
        data = self.map()
        self.assertEqual(data["sections"][0]["title"], self.par.section.name_uk)
        self.assertEqual(data["sections"][0]["paragraphs"][0]["title"], self.par.name_uk)

    def test_german_cookie_falls_back_when_translation_missing(self):
        self.client.cookies["mw_lang"] = "de"
        data = self.map()
        self.assertEqual(data["sections"][0]["title"], self.par.section.name_uk)
        self.assertEqual(data["sections"][0]["paragraphs"][0]["title"], self.par.name_uk)

    def test_german_cookie_uses_translation_when_present(self):
        self.par.section.name_de = "Abschnitt I"
        self.par.section.save()
        self.par.name_de = "Natürliche Zahlen"
        self.par.save()
        self.item2.content_de = "Ziffern"
        self.item2.save()
        self.client.cookies["mw_lang"] = "de"
        data = self.map()
        self.assertEqual(data["sections"][0]["title"], "Abschnitt I")
        self.assertEqual(data["sections"][0]["paragraphs"][0]["title"], "Natürliche Zahlen")
        _, l2, _ = self.lessons(data)
        self.assertEqual(l2["title"], "Ziffern")


class GradesListTests(MapFixture):
    def test_summary(self):
        data = self.client.get(reverse("api_grades")).json()
        self.assertEqual(len(data), 1)
        g = data[0]
        self.assertEqual((g["number"], g["subject"], g["sections"], g["lessons"], g["playable_lessons"]),
                         (5, "math", 1, 3, 2))
        self.assertEqual((g["stars"], g["max_stars"]), (0, 9))
        self.assertEqual(g["current"], {"kind": "item", "id": self.item.pk, "number": 1})
        for key in ("author", "year"):
            self.assertIn(key, g)


class MeStarsTests(MapFixture):
    def test_me_has_stars(self):
        self.assertEqual(self.client.get(reverse("api_me")).json()["stars"], 0)
        self.bind_client_to_player()
        record_answer(self.player, self.s21, "1396")
        self.assertEqual(self.client.get(reverse("api_me")).json()["stars"], 1)

    def test_me_history_counts_todays_points_only(self):
        self.bind_client_to_player()
        record_answer(self.player, self.s21, "1396")
        history = self.client.get(reverse("api_me")).json()["history"]
        self.assertEqual(len(history), 7)
        self.assertEqual(sum(d["points"] for d in history[:-1]), 0)
        self.assertEqual(history[-1]["points"], self.player.points)
        self.assertGreater(history[-1]["points"], 0)


class PlayLockTests(MapFixture):
    def test_locked_lesson_is_403_for_guest(self):
        resp = self.client.get(reverse("api_play_item", args=[self.item2.pk]))
        self.assertEqual((resp.status_code, resp.json()["error"]), (403, "lesson_locked"))

    def test_current_lesson_and_island_fields(self):
        data = self.client.get(reverse("api_play_item", args=[self.item.pk])).json()
        lesson = data["lesson"]
        self.assertEqual((lesson["grade"], lesson["section_number"], lesson["paragraph_number"], lesson["island"],
                          lesson["state"]), (5, 1, 1, 1, "current"))

    def test_staff_bypasses_lock(self):
        User.objects.create_user("teacher", password="x", is_staff=True)
        self.client.login(username="teacher", password="x")
        self.assertEqual(self.client.get(reverse("api_play_item", args=[self.item2.pk])).status_code, 200)

    def test_lock_does_not_leak_into_other_apis(self):
        # перевірка відповіді й теорія не блокуються: лише старт гри
        self.assertEqual(self.client.get(reverse("api_item", args=[self.item2.pk])).status_code, 200)
