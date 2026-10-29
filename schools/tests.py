"""Школи: верифікує лише superuser; верифікована школа сама керує своїми вчителями."""
import json

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from . import services as svc
from .models import School, SchoolMembership


class SchoolRulesTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser("root", password="pw-12345678")
        self.director = User.objects.create_user("director", password="pw-12345678")
        self.teacher = User.objects.create_user("teacher", password="pw-12345678")
        self.stranger = User.objects.create_user("stranger", password="pw-12345678")
        self.school = svc.register_school(self.director, name="Ліцей №1", country="UA",
                                          official_number="137456", city="Київ")

    def test_registration_is_pending_and_registrant_is_school_admin(self):
        self.assertEqual(self.school.status, School.STATUS_PENDING)
        self.assertTrue(svc.is_school_admin(self.director, self.school))

    def test_unverified_school_cannot_add_teachers(self):
        with self.assertRaises(PermissionDenied):
            svc.add_teacher(self.director, self.school, self.teacher)

    def test_only_superuser_verifies(self):
        with self.assertRaises(PermissionDenied):
            svc.verify_school(self.director, self.school)
        svc.verify_school(self.root, self.school)
        self.school.refresh_from_db()
        self.assertTrue(self.school.is_verified)
        self.assertEqual(self.school.verified_by, self.root)
        self.assertIsNotNone(self.school.verified_at)

    def test_verified_school_adds_and_removes_teachers_alone(self):
        svc.verify_school(self.root, self.school)
        m = svc.add_teacher(self.director, self.school, self.teacher)
        self.assertEqual((m.role, m.added_by), (SchoolMembership.ROLE_TEACHER, self.director))
        with self.assertRaises(svc.AlreadyMember):
            svc.add_teacher(self.director, self.school, self.teacher)
        svc.remove_teacher(self.director, self.school, self.teacher)
        self.assertFalse(SchoolMembership.objects.filter(user=self.teacher).exists())

    def test_teacher_and_stranger_cannot_manage_staff(self):
        svc.verify_school(self.root, self.school)
        svc.add_teacher(self.director, self.school, self.teacher)
        for user in (self.teacher, self.stranger):
            with self.assertRaises(PermissionDenied):
                svc.add_teacher(user, self.school, self.stranger)

    def test_school_admin_cannot_remove_school_admin(self):
        svc.verify_school(self.root, self.school)
        with self.assertRaises(PermissionDenied):
            svc.remove_teacher(self.director, self.school, self.director)

    def test_revoking_verification_removes_rights_immediately(self):
        svc.verify_school(self.root, self.school)
        svc.reject_school(self.root, self.school)
        self.assertFalse(svc.can_manage_staff(self.director, self.school))

    def test_official_number_unique_per_country(self):
        with self.assertRaises(ValidationError):
            svc.register_school(self.stranger, name="Дубль", country="UA", official_number="137456")
        other = svc.register_school(self.stranger, name="Gymnasium", country="DE", official_number="137456")
        self.assertEqual(other.country, "DE")

    def test_db_forbids_verified_without_date(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            School.objects.filter(pk=self.school.pk).update(status=School.STATUS_VERIFIED)


class SchoolClassRulesTests(TestCase):
    """Клас (група учнів), яку веде вчитель — FE-0640."""

    def setUp(self):
        self.root = User.objects.create_superuser("root", password="pw-12345678")
        self.director = User.objects.create_user("director", password="pw-12345678")
        self.teacher = User.objects.create_user("teacher", password="pw-12345678")
        self.other_teacher = User.objects.create_user("other_teacher", password="pw-12345678")
        self.student = User.objects.create_user("student", password="pw-12345678")
        self.school = svc.register_school(self.director, name="Ліцей №1", country="UA",
                                          official_number="137456", city="Київ")
        svc.verify_school(self.root, self.school)
        svc.add_teacher(self.director, self.school, self.teacher)
        svc.add_teacher(self.director, self.school, self.other_teacher)

    def test_unverified_school_cannot_have_classes(self):
        school = svc.register_school(self.director, name="Новий ліцей", country="UA", official_number="999")
        with self.assertRaises(PermissionDenied):
            svc.create_class(self.teacher, school, "5-А")

    def test_only_teacher_creates_class(self):
        with self.assertRaises(PermissionDenied):
            svc.create_class(self.director, self.school, "5-А")  # школа-адмін, не вчитель
        school_class = svc.create_class(self.teacher, self.school, "5-А")
        self.assertEqual((school_class.teacher, school_class.school), (self.teacher, self.school))

    def test_teacher_manages_own_class_roster(self):
        school_class = svc.create_class(self.teacher, self.school, "5-А")
        m = svc.add_student(self.teacher, school_class, self.student)
        self.assertEqual((m.school_class, m.user, m.added_by), (school_class, self.student, self.teacher))
        with self.assertRaises(svc.AlreadyInClass):
            svc.add_student(self.teacher, school_class, self.student)
        svc.remove_student(self.teacher, school_class, self.student)
        self.assertFalse(school_class.students.filter(user=self.student).exists())

    def test_other_teacher_cannot_manage_foreign_class(self):
        school_class = svc.create_class(self.teacher, self.school, "5-А")
        with self.assertRaises(PermissionDenied):
            svc.add_student(self.other_teacher, school_class, self.student)

    def test_school_admin_and_superuser_manage_any_class(self):
        school_class = svc.create_class(self.teacher, self.school, "5-А")
        svc.add_student(self.director, school_class, self.student)
        svc.remove_student(self.root, school_class, self.student)
        self.assertFalse(school_class.students.exists())


class SchoolApiTests(TestCase):
    def setUp(self):
        self.root = User.objects.create_superuser("root", password="pw-12345678")
        self.director = User.objects.create_user("director", password="pw-12345678")
        self.teacher = User.objects.create_user("teacher", password="pw-12345678")

    def post(self, url, data):
        return self.client.post(url, json.dumps(data), content_type="application/json")

    def test_full_flow(self):
        self.assertEqual(self.client.get("/api/schools/mine/").status_code, 401)
        self.client.force_login(self.director)
        r = self.post("/api/schools/", {"name": "Gymnasium Mitte", "country": "DE", "official_number": "02Y01"})
        self.assertEqual(r.status_code, 201)
        school_id = r.json()["id"]
        self.assertEqual(r.json()["status"], "pending")
        self.assertEqual(self.post("/api/schools/", {"name": "X", "country": "DE",
                                                     "official_number": "02Y01"}).status_code, 409)

        r = self.post(f"/api/schools/{school_id}/staff/", {"username": "teacher"})
        self.assertEqual((r.status_code, r.json()["error"]), (403, "forbidden"))

        svc.verify_school(self.root, School.objects.get(pk=school_id))
        r = self.post(f"/api/schools/{school_id}/staff/", {"username": "teacher"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.post(f"/api/schools/{school_id}/staff/", {"username": "teacher"}).status_code, 409)
        self.assertEqual(self.post(f"/api/schools/{school_id}/staff/", {"username": "nobody"}).status_code, 404)

        staff = self.client.get(f"/api/schools/{school_id}/staff/").json()["staff"]
        self.assertEqual(sorted(m["username"] for m in staff), ["director", "teacher"])

        r = self.client.delete(f"/api/schools/{school_id}/staff/{self.teacher.pk}/")
        self.assertEqual(r.status_code, 204)

    def test_outsider_cannot_see_staff(self):
        school = svc.register_school(self.director, name="Ліцей", country="UA", official_number="5555")
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(f"/api/schools/{school.pk}/staff/").status_code, 403)


class SchoolClassApiTests(TestCase):
    """CRUD-ендпоінти класу (групи учнів вчителя) і його складу — FE-0640."""

    def setUp(self):
        self.root = User.objects.create_superuser("root", password="pw-12345678")
        self.director = User.objects.create_user("director", password="pw-12345678")
        self.teacher = User.objects.create_user("teacher", password="pw-12345678")
        self.student = User.objects.create_user("student", password="pw-12345678")
        self.school = svc.register_school(self.director, name="Ліцей №1", country="UA", official_number="137456")
        svc.verify_school(self.root, self.school)
        svc.add_teacher(self.director, self.school, self.teacher)

    def post(self, url, data):
        return self.client.post(url, json.dumps(data), content_type="application/json")

    def test_full_flow(self):
        self.assertEqual(self.client.get("/api/classes/mine/").status_code, 401)

        self.client.force_login(self.director)
        r = self.post("/api/classes/", {"school_id": self.school.pk, "name": "5-А"})
        self.assertEqual((r.status_code, r.json()["error"]), (403, "forbidden"))   # адмін, не вчитель

        self.client.force_login(self.teacher)
        r = self.post("/api/classes/", {"school_id": self.school.pk, "name": "5-А"})
        self.assertEqual(r.status_code, 201)
        class_id = r.json()["id"]
        self.assertEqual((r.json()["school_id"], r.json()["teacher_username"], r.json()["student_count"]),
                         (self.school.pk, "teacher", 0))

        mine = self.client.get("/api/classes/mine/").json()["classes"]
        self.assertEqual([c["id"] for c in mine], [class_id])

        r = self.post(f"/api/classes/{class_id}/students/", {"username": "student"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.post(f"/api/classes/{class_id}/students/", {"username": "student"}).status_code, 409)
        self.assertEqual(self.post(f"/api/classes/{class_id}/students/", {"username": "nobody"}).status_code, 404)

        students = self.client.get(f"/api/classes/{class_id}/students/").json()["students"]
        self.assertEqual([s["username"] for s in students], ["student"])

        r = self.client.delete(f"/api/classes/{class_id}/students/{self.student.pk}/")
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.client.get(f"/api/classes/{class_id}/students/").json()["students"], [])

    def test_school_admin_sees_class_in_mine_but_not_as_teacher(self):
        school_class = svc.create_class(self.teacher, self.school, "5-А")
        self.client.force_login(self.director)
        mine = self.client.get("/api/classes/mine/").json()["classes"]
        self.assertEqual([c["id"] for c in mine], [school_class.pk])

    def test_outsider_has_no_classes_and_cannot_see_roster(self):
        school_class = svc.create_class(self.teacher, self.school, "5-А")
        stranger = User.objects.create_user("stranger", password="pw-12345678")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get("/api/classes/mine/").json()["classes"], [])
        self.assertEqual(self.client.get(f"/api/classes/{school_class.pk}/students/").status_code, 403)
