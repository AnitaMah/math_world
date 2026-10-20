"""Правила для шкіл і їхнього персоналу (бізнес-логіка, без HTTP).

Хто що може:
- будь-який залогінений користувач може зареєструвати школу → статус «pending», він стає її адміністратором;
- лише superuser (адміністратор платформи) верифікує або відхиляє школу;
- адміністратор **верифікованої** школи сам додає й видаляє її вчителів;
- поки школа не верифікована (або її відхилили), додавати персонал може лише superuser.

Права перевіряються щоразу «наживо»: якщо школу відкликали, її адміністратор одразу втрачає право.
"""
from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import School, SchoolMembership


class AlreadyMember(Exception):
    """Користувач уже належить до цієї школи."""


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


__all__ = ["AlreadyMember", "ValidationError", "add_teacher", "can_manage_staff", "can_view_staff",
           "is_school_admin", "register_school", "reject_school", "remove_teacher", "verify_school"]
