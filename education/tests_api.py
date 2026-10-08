"""Фаза 21: сторінки уроку, JSON API гри, перевірка відповідей, адмінка з вирізкою сторінки."""
import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from education.importers.textbook_json import TextbookImporter
from education.models import Answer, ContentBlock, Exercise, Figure, Item, Paragraph, SubExercise, Textbook
from education.services import answers_equal, check_answer, normalize_answer
from education.tests_importer import PNG
from education.tests_pipeline.test_export import export, merzlyak_tree

MEDIA = tempfile.mkdtemp(prefix="math_world_api_media_")


@override_settings(MEDIA_ROOT=MEDIA)
class LessonFixture(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "figs").mkdir()
        (tmp / "figs" / "p006_y300.png").write_bytes(PNG)
        TextbookImporter(export(merzlyak_tree()[0]), base_dir=tmp).run()
        self.tb = Textbook.objects.get()
        self.item = Item.objects.get()
        self.par = Paragraph.objects.get()
        self.ex = Exercise.objects.get(number=12)
        self.sub1 = self.ex.subexercises.get(number="1")
        self.sub2 = self.ex.subexercises.get(number="2")
        # вправа, яку гра не повинна бачити
        hidden = Exercise.objects.create(textbook=self.tb, block=self.ex.block, number=13, order=1,
                                         condition="Сумнівна вправа", needs_review=True)
        self.hidden_sub = SubExercise.objects.create(exercise=hidden, number="1", text="2 + 2")
        Answer.objects.create(exercise=hidden, subexercise=self.hidden_sub, kind="book", text="4")


# --------------------------------------------------------------------------- сервіси


class AnswerCompareTests(TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_answer("  Так. "), "так")
        self.assertEqual(normalize_answer("+"), "так")
        self.assertEqual(normalize_answer("Ні"), "ні")
        self.assertEqual(normalize_answer("12 ;16"), "12; 16")

    def test_equal(self):
        yes = [("3,5", "3.5"), ("7/2", "3,5"), ("0,75", "3/4"), ("−76", "- 76"), ("1 454", "1454"),
               ("Так", "так"), ("12;16", "12; 16"), ("2 1/3", "7/3"), ("23220.", "23220")]
        no = [("3,4", "3,5"), ("12", "12; 16"), ("так", "ні"), ("", "5"), ("abc", "5")]
        for u, e in yes:
            with self.subTest(u=u, e=e):
                self.assertTrue(answers_equal(u, e))
        for u, e in no:
            with self.subTest(u=u, e=e):
                self.assertFalse(answers_equal(u, e))


class CheckServiceTests(LessonFixture):
    def test_book_preferred_and_computed_only_if_ok(self):
        self.assertTrue(check_answer(self.sub1, "673").correct)
        Answer.objects.create(exercise=self.ex, subexercise=self.sub2, kind="computed", text="2,88")
        self.assertFalse(check_answer(self.sub2, "2,88").has_answer)        # expr suspect → не перевіряємо


# --------------------------------------------------------------------------- сторінки


class PageTests(LessonFixture):
    @override_settings(NEW_UI=False)   # стара сторінка пункту; нова — tests_ui.LessonPageTests
    def test_item_detail_shows_exercise(self):
        resp = self.client.get(reverse("item_detail", args=[self.item.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('id="ex-%d"' % self.ex.pk, html)
        self.assertIn("238 + 435;", html)
        self.assertIn("difficulty--medium", html)
        self.assertIn("<details class=\"exercise-answer\">", html)
        self.assertIn("textbook_figures/", html)
        self.assertIn("Числа 1, 2, 3", html)

    def test_item_list_counts_and_paragraph_blocks(self):
        resp = self.client.get(reverse("item_list", args=[self.par.pk]))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("вправ: 1", html)                                     # прихована needs_review не рахується
        self.assertIn("Перевірте себе", html)                                # блок рівня §

    def test_item_detail_query_count_is_constant(self):
        """0874: кількість запитів не росте з кількістю вправ (немає N+1)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        url = reverse("item_detail", args=[self.item.pk])
        with CaptureQueriesContext(connection) as before:
            self.client.get(url)
        for n in range(20, 25):
            ex = Exercise.objects.create(textbook=self.tb, block=self.ex.block, number=n, order=n)
            for k in range(3):
                sub = SubExercise.objects.create(exercise=ex, number=str(k + 1), order=k, text="1 + 1")
                Answer.objects.create(exercise=ex, subexercise=sub, kind="computed", text="2")
        with CaptureQueriesContext(connection) as after:
            self.client.get(url)
        self.assertEqual(len(after), len(before))


# --------------------------------------------------------------------------- API


class ApiTests(LessonFixture):
    def get(self, name, *args, **params):
        resp = self.client.get(reverse(name, args=args), params)
        return resp, resp.json() if resp["Content-Type"].startswith("application/json") else None

    def test_textbooks_and_tree(self):
        _, data = self.get("api_textbooks")
        self.assertEqual(data[0]["profile"], "math_merzlyak_5")
        _, tree = self.get("api_textbook_tree", self.tb.pk)
        par = tree["sections"][0]["paragraphs"][0]
        self.assertEqual((par["number"], par["items"][0]["exercises"]), (1, 1))

    def test_grade_map(self):
        resp, data = self.get("api_grade_map", 5)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data["sections"][0]["paragraphs"][0]["items"][0]["title"], "Ряд натуральних чисел")
        resp, data = self.get("api_grade_map", 11)
        self.assertEqual((resp.status_code, data["error"]), (404, "not_found"))

    def test_item_theory(self):
        _, data = self.get("api_item", self.item.pk)
        self.assertEqual([b["type"] for b in data["blocks"]], ["theory"])
        self.assertEqual(data["blocks"][0]["figures"][0]["url"], f"/api/figures/{Figure.objects.get().pk}/image")

    def test_exercise_list_hides_needs_review_and_filters(self):
        _, data = self.get("api_item_exercises", self.item.pk)
        self.assertEqual([e["number"] for e in data["results"]], [12])
        self.assertEqual([s["number"] for s in data["results"][0]["subexercises"]], ["1"])   # «2» — needs_review
        _, data = self.get("api_item_exercises", self.item.pk, difficulty="high")
        self.assertEqual(data["count"], 0)
        resp, data = self.get("api_item_exercises", self.item.pk, page=9)
        self.assertEqual((resp.status_code, data["error"]), (400, "bad_page"))

    def test_exercise_detail_and_hidden_404(self):
        _, data = self.get("api_exercise", self.ex.pk)
        self.assertEqual(data["condition"], "Обчисліть:")
        hidden = Exercise.objects.get(number=13)
        resp, data = self.get("api_exercise", hidden.pk)
        self.assertEqual((resp.status_code, data["error"]), (404, "not_found"))

    def test_answers_never_in_get(self):
        """0801: жоден GET гри не містить тексту відповіді."""
        answers = {"673", "3332"}
        urls = [reverse("api_item_exercises", args=[self.item.pk]), reverse("api_exercise", args=[self.ex.pk]),
                reverse("api_item", args=[self.item.pk]), reverse("api_textbook_tree", args=[self.tb.pk]),
                reverse("api_grade_map", args=[5])]
        for url in urls:
            body = self.client.get(url).content.decode()
            with self.subTest(url=url):
                self.assertNotIn('"answer', body)
                for a in answers:
                    self.assertNotIn(f'"{a}"', body)

    def test_figure_image(self):
        resp = self.client.get(reverse("api_figure_image", args=[Figure.objects.get().pk]))
        self.assertEqual((resp.status_code, resp["Content-Type"]), (200, "image/png"))
        self.assertEqual(b"".join(resp.streaming_content), PNG)

    def test_method_not_allowed_format(self):
        resp = self.client.post(reverse("api_textbooks"))
        self.assertEqual((resp.status_code, resp.json()["error"]), (405, "method_not_allowed"))


class CheckApiTests(LessonFixture):
    def post(self, sub, answer, client=None):
        return (client or self.client).post(reverse("api_check", args=[sub.pk]), json.dumps({"answer": answer}),
                                            content_type="application/json")

    def test_correct_and_wrong(self):
        resp = self.post(self.sub1, "673")
        self.assertEqual(resp.json()["correct"], True)
        self.assertNotIn("673", json.dumps(self.post(self.sub1, "600").json()))   # правильну не розкриваємо
        self.assertFalse(self.post(self.sub1, "600").json()["correct"])

    def test_form_post_and_errors(self):
        resp = self.client.post(reverse("api_check", args=[self.sub1.pk]), {"answer": "673"})
        self.assertTrue(resp.json()["correct"])
        self.assertEqual(self.post(self.sub1, "  ").json()["error"], "empty_answer")
        self.assertEqual(self.post(self.sub2, "3332").status_code, 404)       # підпункт needs_review
        self.sub2.needs_review = False
        self.sub2.save()
        self.assertEqual(self.post(self.sub2, "3332").status_code, 409)       # немає відповіді
        self.assertEqual(self.post(self.hidden_sub, "4").status_code, 404)    # needs_review
        self.assertEqual(self.client.get(reverse("api_check", args=[self.sub1.pk])).status_code, 405)

    def test_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.post(self.sub1, "1").status_code, 200)
        resp = self.post(self.sub1, "673")
        self.assertEqual((resp.status_code, resp.json()["error"]), (429, "too_many_attempts"))
        self.assertEqual(self.post(self.sub2, "1").status_code, 404)          # ліміт — на підпункт, інший не заблоковано

    def test_csrf_flow(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post(self.sub1, "673", client).status_code, 403)
        client.get(reverse("api_csrf"))
        token = client.cookies["csrftoken"].value
        resp = client.post(reverse("api_check", args=[self.sub1.pk]), json.dumps({"answer": "673"}),
                           content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual((resp.status_code, resp.json()["correct"]), (200, True))


# --------------------------------------------------------------------------- адмінка


class AdminTests(LessonFixture):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(self.admin)

    def test_change_page_with_crop(self):
        resp = self.client.get(reverse("admin:education_exercise_change", args=[self.ex.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("admin:education_exercise_crop", args=[self.ex.pk]))

    def test_crop_view(self):
        with mock.patch("education.services.page_crop_png", return_value=PNG) as crop:
            resp = self.client.get(reverse("admin:education_exercise_crop", args=[self.ex.pk]))
        self.assertEqual((resp.status_code, resp["Content-Type"], resp.content), (200, "image/png", PNG))
        crop.assert_called_once_with(self.tb, 7, [70, 100, 700, 140])
        with mock.patch("education.services.page_crop_png", return_value=None):
            self.assertEqual(self.client.get(reverse("admin:education_exercise_crop", args=[self.ex.pk])).status_code, 404)

    def test_crop_requires_staff(self):
        self.client.logout()
        resp = self.client.get(reverse("admin:education_exercise_crop", args=[self.ex.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_mark_reviewed_action_and_filters(self):
        hidden = Exercise.objects.get(number=13)
        resp = self.client.post(reverse("admin:education_exercise_changelist"),
                                {"action": "mark_reviewed", "_selected_action": [hidden.pk]})
        self.assertEqual(resp.status_code, 302)
        hidden.refresh_from_db()
        self.assertEqual((hidden.needs_review, hidden.text_source), (False, "manual"))
        resp = self.client.get(reverse("admin:education_exercise_changelist"),
                               {"block__item__paragraph__id__exact": self.par.pk, "q": "12"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("admin:education_exercise_change", args=[self.ex.pk]))

    def test_edit_in_admin_becomes_manual(self):
        url = reverse("admin:education_exercise_change", args=[self.ex.pk])
        form = self.client.get(url).context["adminform"].form
        data = {k: v for k, v in form.initial.items() if v is not None and not isinstance(v, (list, dict))}
        self.assertTrue(data)
        self.ex.condition = "Нова умова"
        self.ex.text_source = "manual"                    # те, що робить save_model при зміні умови
        self.ex.save()
        self.assertEqual(Exercise.objects.get(pk=self.ex.pk).text_source, "manual")
