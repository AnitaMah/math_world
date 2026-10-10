"""/review/ для персоналу: черга, правка, пропуск, журнал, лічильники, експорт/імпорт правок."""
import copy
import io
import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from education import review
from education.importers.textbook_json import TextbookImporter
from education.models import Exercise, ManualEdit, SubExercise, Textbook
from education.tests_importer import MEDIA, PNG, blocks_of, fixture_json


@override_settings(MEDIA_ROOT=MEDIA)
class ReviewTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "figs").mkdir()
        (self.tmp / "figs" / "p006_y300.png").write_bytes(PNG)
        self.data = fixture_json()
        TextbookImporter(self.data, base_dir=self.tmp).run()
        self.ex = Exercise.objects.get()
        self.sub1, self.sub2 = self.ex.subexercises.order_by("order")
        SubExercise.objects.filter(pk__in=[self.sub1.pk, self.sub2.pk]).update(needs_review=True)
        self.staff = User.objects.create_user("staff", password="x", is_staff=True)
        self.client.force_login(self.staff)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def post(self, kind, obj, **data):
        return self.client.post(reverse("review_detail", args=[kind, obj.pk]), data)

    # --- доступ
    def test_anonymous_redirected(self):
        self.client.logout()
        for url in (reverse("review_index"), reverse("review_detail", args=["subexercise", self.sub1.pk]),
                    reverse("review_crop", args=["subexercise", self.sub1.pk])):
            self.assertEqual(self.client.get(url).status_code, 302, url)

    def test_non_staff_redirected(self):
        user = User.objects.create_user("kid", password="x")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("review_index")).status_code, 302)

    # --- перегляд
    def test_index_and_counters(self):
        r = self.client.get(reverse("review_index"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["total"], 2)
        (paragraph, n), = review.counters()
        self.assertEqual(n, 2)
        self.assertContains(r, f"§ {paragraph.number}")

    def test_detail_renders(self):
        r = self.client.get(reverse("review_detail", args=["subexercise", self.sub1.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.sub1.text)
        self.assertEqual(self.client.get(reverse("review_detail", args=["bogus", 1])).status_code, 404)

    def test_crop_view(self):
        Exercise.objects.filter(pk=self.ex.pk).update(source_page=7, source_bbox=[0, 0, 10, 10])
        with mock.patch("education.services.page_crop_png", return_value=PNG):
            r = self.client.get(reverse("review_crop", args=["subexercise", self.sub1.pk]))
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "image/png"))
        with mock.patch("education.services.page_crop_png", return_value=None):
            self.assertEqual(self.client.get(reverse("review_crop", args=["exercise", self.ex.pk])).status_code, 404)

    # --- дії
    def test_save_edit(self):
        r = self.post("subexercise", self.sub1, action="save", text="100 + 200;")
        self.assertEqual(r.status_code, 302)
        self.assertIn(f"/subexercise/{self.sub2.pk}/", r["Location"])         # перейшли до наступного
        self.sub1.refresh_from_db()
        self.assertEqual((self.sub1.text, self.sub1.text_source, self.sub1.needs_review), ("100 + 200;", "manual", False))
        edit = ManualEdit.objects.get()
        self.assertEqual((edit.action, edit.user, edit.sub_number, edit.exercise_number), ("edit", self.staff, "1", 12))
        self.assertEqual(edit.new_text, "100 + 200;")

    def test_confirm_keeps_text(self):
        old = self.sub2.text
        self.post("subexercise", self.sub2, action="confirm")
        self.sub2.refresh_from_db()
        self.assertEqual((self.sub2.text, self.sub2.text_source, self.sub2.needs_review), (old, "manual", False))
        self.assertEqual(ManualEdit.objects.get().action, "confirm")

    def test_skip_hides_from_queue_but_stays_hidden_in_game(self):
        self.post("subexercise", self.sub1, action="skip")
        self.sub1.refresh_from_db()
        self.assertTrue(self.sub1.needs_review and self.sub1.review_skipped)
        self.assertEqual(len(review.queue()), 1)
        self.assertEqual(len(review.queue(skipped=True)), 1)
        self.post("subexercise", self.sub1, action="unskip")
        self.assertEqual(len(review.queue()), 2)

    def test_exercise_edit(self):
        Exercise.objects.filter(pk=self.ex.pk).update(needs_review=True)
        self.post("exercise", self.ex, action="save", text="Нова умова")
        self.ex.refresh_from_db()
        self.assertEqual((self.ex.condition, self.ex.text_source, self.ex.needs_review), ("Нова умова", "manual", False))

    def test_bad_action(self):
        self.assertEqual(self.post("subexercise", self.sub1, action="boom").status_code, 400)

    # --- переживає повторний імпорт
    def test_edits_survive_reimport(self):
        self.post("subexercise", self.sub1, action="save", text="100 + 200;")
        self.post("subexercise", self.sub2, action="skip")
        data = copy.deepcopy(self.data)
        for s in blocks_of(data)[1]["exercises"][0]["subexercises"]:
            s["text"] = "знову OCR"
        TextbookImporter(data, base_dir=self.tmp).run()
        self.sub1.refresh_from_db(); self.sub2.refresh_from_db()
        self.assertEqual(self.sub1.text, "100 + 200;")
        self.assertTrue(self.sub2.needs_review and self.sub2.review_skipped)

    # --- експорт / імпорт
    def test_export_import_round_trip(self):
        self.post("subexercise", self.sub1, action="save", text="1 + 1;")
        self.post("subexercise", self.sub1, action="save", text="100 + 200;")      # лишається лише остання
        self.post("subexercise", self.sub2, action="skip")
        out = self.tmp / "edits.json"
        call_command("export_manual_edits", out=str(out), stdout=io.StringIO())
        edits = json.loads(out.read_text(encoding="utf-8"))["edits"]
        self.assertEqual(sorted((e["sub"], e["action"]) for e in edits), [("1", "edit"), ("2", "skip")])

        # «свіжа» БД: скидаємо стан і застосовуємо JSON
        SubExercise.objects.update(text_source="ocr", needs_review=True, review_skipped=False)
        SubExercise.objects.filter(pk=self.sub1.pk).update(text="OCR")
        buf = io.StringIO()
        call_command("import_manual_edits", json=str(out), stdout=buf)
        self.assertIn("застосовано 2", buf.getvalue())
        self.sub1.refresh_from_db(); self.sub2.refresh_from_db()
        self.assertEqual((self.sub1.text, self.sub1.needs_review, self.sub1.text_source), ("100 + 200;", False, "manual"))
        self.assertTrue(self.sub2.review_skipped and self.sub2.needs_review)
        buf = io.StringIO()                                                        # ідемпотентно
        call_command("import_manual_edits", json=str(out), stdout=buf)
        self.assertIn("застосовано 0", buf.getvalue())

    def test_import_reports_missing(self):
        out = self.tmp / "e.json"
        out.write_text(json.dumps({"edits": [{"profile_code": "math_merzlyak_5", "kind": "exercise", "block_type": "exercise",
                                              "number": 9999, "page": 1, "sub": "", "action": "edit", "text": "x"}]}))
        buf = io.StringIO()
        call_command("import_manual_edits", json=str(out), stdout=buf)
        self.assertIn("не знайдено 1", buf.getvalue())
