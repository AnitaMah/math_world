"""JSON API для шкіл (той самий формат помилок, що й education/api.py).

    GET    /api/schools/mine/                      мої школи, роль і чи можу керувати персоналом
    POST   /api/schools/                           заявка на реєстрацію школи → pending
    GET    /api/schools/<id>/staff/                персонал школи (для членів школи і superuser)
    POST   /api/schools/<id>/staff/                {"username": "..."} — додати вчителя (лише верифікована школа)
    DELETE /api/schools/<id>/staff/<user_id>/      прибрати вчителя
    GET    /api/classes/mine/                      класи, якими я керую (веду сам або адміную школу)
    POST   /api/classes/                           {"school_id": ., "name": "..."} — створити клас (лише вчитель)
    GET    /api/classes/<id>/students/              склад класу
    POST   /api/classes/<id>/students/              {"username": "..."} — додати учня
    DELETE /api/classes/<id>/students/<user_id>/    прибрати учня

% учнів класу зі зіркою на уроці/вузлі — не окремий ендпоінт, а `class_pct` на
`GET /api/grades/<n>/map/?class_id=<id>` (education/api.py, education/grade_map.py);
`GET /api/me/` віддає `is_teacher` — контракт для FE-0645 (`docs/frontend/DECISIONS.md`).

api_error/api_view/ok лишаються спільними HTTP-хелперами в education.api (BE-S03:
генерична обгортка відповіді, не каталожна логіка — крос-застосунковий імпорт тут
нормальний, на відміну від моделей).
"""
from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from education.api import api_error, api_view, ok

from . import services as svc
from .models import SCHOOL_COUNTRY_CHOICES, School, SchoolClass, SchoolClassStudent, SchoolMembership


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


def class_dict(c: SchoolClass) -> dict:
    return {"id": c.pk, "name": c.name, "school_id": c.school_id, "school_name": c.school.name,
            "teacher_id": c.teacher_id, "teacher_username": c.teacher.username,
            "student_count": c.students.count()}


def student_dict(m: SchoolClassStudent) -> dict:
    return {"user_id": m.user_id, "username": m.user.username, "added_at": m.created_at.isoformat()}


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
def my_classes(request):
    """Класи, якими можу керувати: веду сам або адміную їхню школу (superuser — усі)."""
    if request.user.is_superuser:
        qs = SchoolClass.objects.select_related("school", "teacher")
    else:
        admin_school_ids = SchoolMembership.objects.filter(
            user=request.user, role=SchoolMembership.ROLE_SCHOOL_ADMIN).values_list("school_id", flat=True)
        qs = (SchoolClass.objects.filter(Q(teacher=request.user) | Q(school_id__in=admin_school_ids))
              .select_related("school", "teacher"))
    return ok({"classes": [class_dict(c) for c in qs.order_by("school__name", "name")]})


@api_view
@require_http_methods(["POST"])
@login_required_json
def create_class(request):
    try:
        data = _payload(request)
    except ValueError:
        return api_error(400, "bad_json", "Тіло запиту — не JSON")
    name = (data.get("name") or "").strip()
    school_id = data.get("school_id")
    if not name or not school_id:
        return api_error(400, "missing_fields", "Потрібні name і school_id")
    school = get_object_or_404(School, pk=school_id)
    try:
        school_class = svc.create_class(request.user, school, name[:100])
    except PermissionDenied as exc:
        return api_error(403, "forbidden", str(exc))
    except ValidationError as exc:
        return api_error(400, "invalid", "; ".join(exc.messages))
    return ok_status(201, class_dict(school_class))


@api_view
@require_http_methods(["GET", "POST"])
@login_required_json
def class_students(request, pk):
    school_class = get_object_or_404(SchoolClass, pk=pk)
    if request.method == "GET":
        if not svc.can_manage_class(request.user, school_class):
            return api_error(403, "forbidden", "Немає права переглядати склад цього класу")
        members = school_class.students.select_related("user")
        return ok({"class": class_dict(school_class), "students": [student_dict(m) for m in members]})

    try:
        data = _payload(request)
    except ValueError:
        return api_error(400, "bad_json", "Тіло запиту — не JSON")
    username = (data.get("username") or "").strip()
    if not username:
        return api_error(400, "empty_username", "Вкажіть username учня")
    try:
        if not svc.can_manage_class(request.user, school_class):   # не розкриваємо, чи існує такий користувач
            raise PermissionDenied("Немає права керувати складом цього класу")
        student = get_object_or_404(get_user_model(), username=username)
        membership = svc.add_student(request.user, school_class, student)
    except PermissionDenied as exc:
        return api_error(403, "forbidden", str(exc))
    except svc.AlreadyInClass as exc:
        return api_error(409, "already_in_class", str(exc))
    return ok_status(201, student_dict(membership))


@api_view
@require_http_methods(["DELETE"])
@login_required_json
def class_student(request, pk, user_id):
    school_class = get_object_or_404(SchoolClass, pk=pk)
    student = get_object_or_404(get_user_model(), pk=user_id)
    try:
        svc.remove_student(request.user, school_class, student)
    except PermissionDenied as exc:
        return api_error(403, "forbidden", str(exc))
    return HttpResponse(status=204)


def ok_status(status: int, data):
    response = ok(data)
    response.status_code = status
    return response
