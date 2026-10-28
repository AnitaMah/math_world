"""JSON API для шкіл (той самий формат помилок, що й education/api.py).

    GET    /api/schools/mine/                      мої школи, роль і чи можу керувати персоналом
    POST   /api/schools/                           заявка на реєстрацію школи → pending
    GET    /api/schools/<id>/staff/                персонал школи (для членів школи і superuser)
    POST   /api/schools/<id>/staff/                {"username": "..."} — додати вчителя (лише верифікована школа)
    DELETE /api/schools/<id>/staff/<user_id>/      прибрати вчителя
    GET    /api/classes/<id>/grades/<n>/stars/     % учнів класу із зіркою на кожному уроці/вузлі (FE-0645)
"""
from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from . import schools as svc
from .api import api_error, api_view, ok
from .models import SCHOOL_COUNTRY_CHOICES, Grade, School, SchoolClass, SchoolMembership


def login_required_json(view):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return api_error(401, "login_required", "Потрібно увійти")
        return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


def _payload(request):
    if request.content_type == "application/json":
        data = json.loads(request.body or b"{}")
        if not isinstance(data, dict):
            raise ValueError("JSON має бути об'єктом")
        return data
    return request.POST


def school_dict(school: School, user=None) -> dict:
    data = {"id": school.pk, "name": school.name, "country": school.country, "city": school.city,
            "official_number": school.official_number, "status": school.status,
            "is_verified": school.is_verified}
    if user is not None:
        data["can_manage_staff"] = svc.can_manage_staff(user, school)
    return data


def member_dict(m: SchoolMembership) -> dict:
    return {"user_id": m.user_id, "username": m.user.username, "role": m.role,
            "added_at": m.created_at.isoformat()}


@api_view
@require_http_methods(["GET"])
@login_required_json
def my_schools(request):
    memberships = (SchoolMembership.objects.filter(user=request.user).select_related("school")
                   .order_by("school__name"))
    return ok({"schools": [dict(school_dict(m.school, request.user), role=m.role) for m in memberships]})


@api_view
@require_http_methods(["POST"])
@login_required_json
def register(request):
    try:
        data = _payload(request)
    except ValueError:
        return api_error(400, "bad_json", "Тіло запиту — не JSON")
    name = (data.get("name") or "").strip()
    number = (data.get("official_number") or "").strip()
    country = (data.get("country") or "UA").strip().upper()
    if not name or not number:
        return api_error(400, "missing_fields", "Потрібні name і official_number")
    if country not in dict(SCHOOL_COUNTRY_CHOICES):
        return api_error(400, "bad_country", "Країна: UA або DE")
    try:
        school = svc.register_school(request.user, name=name[:255], country=country,
                                     official_number=number, city=(data.get("city") or "")[:100])
    except ValidationError as exc:
        if "__all__" in getattr(exc, "message_dict", {}):
            return api_error(409, "school_exists", "Школа з таким офіційним номером уже зареєстрована")
        return api_error(400, "invalid", "; ".join(exc.messages))
    return ok_status(201, school_dict(school, request.user))


@api_view
@require_http_methods(["GET", "POST"])
@login_required_json
def staff(request, pk):
    school = get_object_or_404(School, pk=pk)
    if request.method == "GET":
        if not svc.can_view_staff(request.user, school):
            return api_error(403, "forbidden", "Ви не належите до цієї школи")
        members = school.memberships.select_related("user")
        return ok({"school": school_dict(school, request.user), "staff": [member_dict(m) for m in members]})

    try:
        data = _payload(request)
    except ValueError:
        return api_error(400, "bad_json", "Тіло запиту — не JSON")
    username = (data.get("username") or "").strip()
    if not username:
        return api_error(400, "empty_username", "Вкажіть username вчителя")
    try:
        if not svc.can_manage_staff(request.user, school):   # не розкриваємо, чи існує такий користувач
            raise PermissionDenied("Школа ще не верифікована" if not school.is_verified
                                   else "Лише адміністратор школи може додавати вчителів")
        teacher = get_object_or_404(get_user_model(), username=username)
        membership = svc.add_teacher(request.user, school, teacher)
    except PermissionDenied as exc:
        return api_error(403, "forbidden", str(exc))
    except svc.AlreadyMember as exc:
        return api_error(409, "already_member", str(exc))
    return ok_status(201, member_dict(membership))


@api_view
@require_http_methods(["DELETE"])
@login_required_json
def staff_member(request, pk, user_id):
    school = get_object_or_404(School, pk=pk)
    teacher = get_object_or_404(get_user_model(), pk=user_id)
    try:
        svc.remove_teacher(request.user, school, teacher)
    except PermissionDenied as exc:
        return api_error(403, "forbidden", str(exc))
    return HttpResponse(status=204)


@api_view
@require_http_methods(["GET"])
@login_required_json
def class_stars(request, pk, number):
    """% учнів класу із зіркою на кожному уроці/вузлі — контракт для FE-0645."""
    from .grade_map import class_star_payload
    from .views import get_lang

    school_class = get_object_or_404(SchoolClass, pk=pk)
    if not svc.can_manage_class(request.user, school_class):
        return api_error(403, "forbidden", "Немає права переглядати статистику цього класу")
    grade = get_object_or_404(Grade, number=number, subject__code=request.GET.get("subject", "math"))
    return ok(class_star_payload(school_class, grade, get_lang(request)))


def ok_status(status: int, data):
    response = ok(data)
    response.status_code = status
    return response
