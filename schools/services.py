"""Правила для шкіл і їхнього персоналу (бізнес-логіка, без HTTP).

Хто що може:
- будь-який залогінений користувач може зареєструвати школу → статус «pending», він стає її адміністратором;
- лише superuser (адміністратор платформи) верифікує або відхиляє школу;
- адміністратор **верифікованої** школи сам додає й видаляє її вчителів;
- поки школа не верифікована (або її відхилили), додавати персонал може лише superuser;
- вчитель верифікованої школи створює власні класи й сам керує їхнім складом учнів;
  адміністратор школи й superuser також можуть керувати складом будь-якого класу школи.

Права перевіряються щоразу «наживо»: якщо школу відкликали, її адміністратор одразу втрачає право.
"""
from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import School, SchoolClass, SchoolClassStudent, SchoolMembership


class AlreadyMember(Exception):
    """Користувач уже належить до цієї школи."""


class AlreadyInClass(Exception):
    """Учень уже в цьому класі."""


def is_school_admin(user, school: School) -> bool:
    if not user.is_authenticated:
        return False
    return SchoolMembership.objects.filter(school=school, user=user,
                                           role=SchoolMembership.ROLE_SCHOOL_ADMIN).exists()


def can_manage_staff(user, school: School) -> bool:
    """Чи може user додавати/видаляти вчителів цієї школи без участі адміністратора платформи."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return school.is_verified and is_school_admin(user, school)


def can_view_staff(user, school: School) -> bool:
    if not user.is_authenticated:
        return False
    return user.is_superuser or SchoolMembership.objects.filter(school=school, user=user).exists()


@transaction.atomic
def register_school(by, *, name: str, country: str, official_number: str, city: str = "") -> School:
    """Школа подає заявку. Реєстратор стає адміністратором школи; верифікує superuser."""
    if not by.is_authenticated:
        raise PermissionDenied("Потрібно увійти")
    school = School(name=name.strip(), country=country, official_number=official_number.strip(),
                    city=city.strip(), created_by=by)
    school.full_clean()          # валідатор номера + унікальність (country, official_number)
    school.save()
    SchoolMembership.objects.create(school=school, user=by, role=SchoolMembership.ROLE_SCHOOL_ADMIN, added_by=by)
    return school


def _require_platform_admin(by):
    if not (by.is_authenticated and by.is_superuser):
        raise PermissionDenied("Лише адміністратор платформи може змінювати статус школи")


def verify_school(by, school: School) -> School:
    _require_platform_admin(by)
    school.status = School.STATUS_VERIFIED
    school.verified_at = timezone.now()
    school.verified_by = by
    school.save(update_fields=["status", "verified_at", "verified_by"])
    return school


def reject_school(by, school: School) -> School:
    """Відхилити заявку або відкликати верифікацію — адміністратор школи одразу втрачає права."""
    _require_platform_admin(by)
    school.status = School.STATUS_REJECTED
    school.verified_at = None
    school.verified_by = None
    school.save(update_fields=["status", "verified_at", "verified_by"])
    return school


def add_teacher(by, school: School, user) -> SchoolMembership:
    if not can_manage_staff(by, school):
        raise PermissionDenied("Школа ще не верифікована" if not school.is_verified
                               else "Лише адміністратор школи може додавати вчителів")
    try:
        with transaction.atomic():
            return SchoolMembership.objects.create(school=school, user=user,
                                                   role=SchoolMembership.ROLE_TEACHER, added_by=by)
    except IntegrityError:
        raise AlreadyMember(f"{user} уже в школі {school.name}") from None


def remove_teacher(by, school: School, user) -> None:
    """Видаляє лише вчителів. Адміністратора школи прибирає тільки адміністратор платформи."""
    if not can_manage_staff(by, school):
        raise PermissionDenied("Немає права керувати персоналом цієї школи")
    membership = SchoolMembership.objects.filter(school=school, user=user).first()
    if membership is None:
        raise SchoolMembership.DoesNotExist(f"{user} не належить до школи {school.name}")
    if membership.role != SchoolMembership.ROLE_TEACHER and not by.is_superuser:
        raise PermissionDenied("Адміністратора школи може прибрати лише адміністратор платформи")
    membership.delete()


def is_teacher(user, school: School) -> bool:
    if not user.is_authenticated:
        return False
    return SchoolMembership.objects.filter(school=school, user=user, role=SchoolMembership.ROLE_TEACHER).exists()


def can_manage_class(user, school_class: SchoolClass) -> bool:
    """Чи може user керувати складом цього класу: сам вчитель класу, адмін школи або superuser."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or school_class.teacher_id == user.pk:
        return True
    return is_school_admin(user, school_class.school)


def create_class(by, school: School, name: str) -> SchoolClass:
    """Вчитель створює свій клас. Потрібна верифікована школа й роль «вчитель» у ній."""
    if not school.is_verified:
        raise PermissionDenied("Школа ще не верифікована")
    if not is_teacher(by, school):
        raise PermissionDenied("Лише вчитель школи може створити клас")
    school_class = SchoolClass(school=school, teacher=by, name=name.strip())
    school_class.full_clean()
    school_class.save()
    return school_class


def add_student(by, school_class: SchoolClass, user) -> SchoolClassStudent:
    if not can_manage_class(by, school_class):
        raise PermissionDenied("Немає права керувати складом цього класу")
    try:
        with transaction.atomic():
            return SchoolClassStudent.objects.create(school_class=school_class, user=user, added_by=by)
    except IntegrityError:
        raise AlreadyInClass(f"{user} уже в класі {school_class.name}") from None


def remove_student(by, school_class: SchoolClass, user) -> None:
    if not can_manage_class(by, school_class):
        raise PermissionDenied("Немає права керувати складом цього класу")
    membership = SchoolClassStudent.objects.filter(school_class=school_class, user=user).first()
    if membership is None:
        raise SchoolClassStudent.DoesNotExist(f"{user} не в класі {school_class.name}")
    membership.delete()


__all__ = ["AlreadyInClass", "AlreadyMember", "ValidationError", "add_student", "add_teacher",
           "can_manage_class", "can_manage_staff", "can_view_staff", "create_class", "is_school_admin",
           "is_teacher", "register_school", "reject_school", "remove_student", "remove_teacher",
           "verify_school"]
