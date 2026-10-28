"""% учнів шкільного класу (групи, яку веде вчитель) із зіркою на уроці/вузлі — FE-0640, контракт для FE-0645."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from education import schools as svc
from education.game import record_answer
from education.models import Player
from education.tests_map_api import MapFixture


class ClassStarsApiTests(MapFixture):
    def setUp(self):
        super().setUp()
        self.root = User.objects.create_superuser("root", password="pw-12345678")
        self.director = User.objects.create_user("director", password="pw-12345678")
        self.teacher = User.objects.create_user("teacher", password="pw-12345678")
        self.alice = User.objects.create_user("alice", password="pw-12345678")
        self.bob = User.objects.create_user("bob", password="pw-12345678")
        self.school = svc.register_school(self.director, name="Ліцей №1", country="UA", official_number="137456")
        svc.verify_school(self.root, self.school)
        svc.add_teacher(self.director, self.school, self.teacher)
        self.school_class = svc.create_class(self.teacher, self.school, "5-А")
        svc.add_student(self.teacher, self.school_class, self.alice)
        svc.add_student(self.teacher, self.school_class, self.bob)
        self.alice_player = Player.objects.create(user=self.alice)
        self.bob_player = Player.objects.create(user=self.bob)

    def url(self, pk=None):
        return reverse("api_class_stars", args=[pk or self.school_class.pk, 5])

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.url()).status_code, 401)

    def test_forbidden_for_outsider(self):
        self.client.force_login(self.alice)      # учень класу, але не керує ним
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_percent_counts_students_with_star(self):
        record_answer(self.alice_player, self.s21, "1396")    # 1 з 3 завдань уроку self.item → 1 зірка
        self.client.force_login(self.teacher)
        data = self.client.get(self.url()).json()
        self.assertEqual((data["class_id"], data["grade"], data["total_students"]),
                         (self.school_class.pk, 5, 2))
        l1 = next(l for l in data["lessons"] if l["kind"] == "item" and l["id"] == self.item.pk)
        self.assertEqual((l1["with_star"], l1["percent"]), (1, 50))
        l2 = next(l for l in data["lessons"] if l["kind"] == "item" and l["id"] == self.item2.pk)
        self.assertEqual((l2["with_star"], l2["percent"]), (0, 0))

    def test_school_admin_and_superuser_can_view(self):
        for user in (self.director, self.root):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url()).status_code, 200)

    def test_other_teacher_cannot_view_foreign_class(self):
        other_teacher = User.objects.create_user("other_teacher", password="pw-12345678")
        svc.add_teacher(self.director, self.school, other_teacher)
        self.client.force_login(other_teacher)
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_empty_class_has_zero_percent_not_error(self):
        empty_class = svc.create_class(self.teacher, self.school, "5-Б")
        self.client.force_login(self.teacher)
        data = self.client.get(self.url(empty_class.pk)).json()
        self.assertEqual(data["total_students"], 0)
        self.assertTrue(data["lessons"])
        self.assertTrue(all(l["percent"] == 0 for l in data["lessons"]))
