"""Школи: верифікує лише superuser; верифікована школа сама керує своїми вчителями."""
import json

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from . import schools as svc
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
