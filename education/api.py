"""JSON API для каталогу (підручники, класи, мапа, теорія уроку, вправи).

Гра (check/solution/play/me) — `game/api.py` (BE-S06, docs/backend/PLAN.md).
Прості ``JsonResponse`` без DRF — рішення в DECISIONS.md.

Правила:
- Вправи з ``needs_review`` сюди не потрапляють (404 для однієї вправи, відфільтровані в списках).
- Усі помилки — ``{"error": "<код>", "detail": "<пояснення>"}`` з відповідним HTTP-статусом.
"""
from __future__ import annotations

import functools

from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import EmptyPage, Paginator
from django.db.models import Prefetch
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from .models import Exercise, Figure, Grade, Item, Paragraph, Section, SubExercise, Textbook
from .serializers import block_dict, exercise_dict, figure_dict, subexercise_dict
from .services import THEORY_BLOCK_TYPES, lesson_exercises, playable_counts

MAX_PAGE_SIZE = 50


def api_error(status: int, error: str, detail: str = "") -> JsonResponse:
    return JsonResponse({"error": error, "detail": detail}, status=status,
                        json_dumps_params={"ensure_ascii": False})


def ok(data) -> JsonResponse:
    return JsonResponse(data, safe=not isinstance(data, list), json_dumps_params={"ensure_ascii": False})


def api_view(view):
    """404/помилки моделей → єдиний формат; 405 від require_* теж обгортаємо."""
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            response = view(request, *args, **kwargs)
        except (Http404, ObjectDoesNotExist) as exc:
            return api_error(404, "not_found", str(exc) or "Не знайдено")
        if response.status_code == 405 and not isinstance(response, JsonResponse):
            return api_error(405, "method_not_allowed", f"Дозволено: {response.get('Allow', '')}")
        return response
    return wrapper


# --------------------------------------------------------------------------- ендпоінти


@api_view
@require_GET
@ensure_csrf_cookie
def csrf(request):
    """Ставить cookie csrftoken — JS гри бере його звідси для POST check."""
    return ok({"csrf": "ok"})


@api_view
@require_GET
def textbooks(request):
    books = Textbook.objects.select_related("subject", "grade").order_by("grade__number", "title")
    return ok([{"id": t.pk, "title": t.title, "author": t.author, "year": t.year, "subject": t.subject.code,
                "grade": t.grade.number, "profile": t.profile_code} for t in books])


def _tree(sections, player=None) -> list[dict]:
    paragraphs = list(Paragraph.objects.filter(section__in=sections).order_by("number")
                      .prefetch_related(Prefetch("item_set", queryset=Item.objects.order_by("number"))))
    items = [i for p in paragraphs for i in p.item_set.all()]
    item_counts, par_counts = playable_counts(items), playable_counts(paragraphs)
    stars: dict[tuple[str, int], int] = {}
    if player is not None:
        for p in player.progress.all():
            stars[("item", p.item_id) if p.item_id else ("paragraph", p.paragraph_id)] = p.stars
    by_section: dict[int, list] = {}
    for p in paragraphs:
        by_section.setdefault(p.section_id, []).append({
            "id": p.pk, "number": p.number, "title": p.name_uk, "exercises": par_counts.get(p.pk, 0),
            "stars": stars.get(("paragraph", p.pk), 0),
            "items": [{"id": i.pk, "number": i.number, "title": (i.content or "").splitlines()[0] if i.content else "",
                       "exercises": item_counts.get(i.pk, 0), "stars": stars.get(("item", i.pk), 0)}
                      for i in p.item_set.all()],
        })
    return [{"id": s.pk, "number": s.number, "title": s.name_uk, "paragraphs": by_section.get(s.pk, [])}
            for s in sections]


@api_view
@require_GET
def textbook_tree(request, textbook_id):
    tb = get_object_or_404(Textbook, pk=textbook_id)
    sections = list(Section.objects.filter(textbook=tb).order_by("number"))
    return ok({"id": tb.pk, "title": tb.title, "sections": _tree(sections)})


@api_view
@require_GET
def grades(request):
    """Класи для екрана «Світ»: підручник, к-сть розділів/уроків, зірки гравця, поточний урок."""
    from game.services import get_player

    from .grade_map import grade_summary, load_grade

    player = get_player(request, create=False)
    qs = Grade.objects.filter(subject__code=request.GET.get("subject", "math")).order_by("number")
    return ok([grade_summary(gm) for gm in (load_grade(g, player) for g in qs) if gm.sections])


@api_view
@require_GET
def grade_map(request, number):
    """Мапа класу (контракт `docs/frontend`): розділи → § → уроки зі станом, зірками, завданнями, блоками.

    `?class_id=` (режим вчителя, FE-0640/0645) — додає поле `class_pct` на кожен урок/вузол: %
    учнів цього шкільного класу із зіркою (`None`, якщо без завдань). Доступно лише тому, хто може
    керувати класом (його вчитель, адмін школи, superuser) — інакше 403.
    """
    from game.services import get_player
    from schools.models import SchoolClass
    from schools.services import can_manage_class

    from .grade_map import class_percent_map, load_grade, map_payload
    from .views import get_lang

    lang = get_lang(request)
    grade = get_object_or_404(Grade, number=number, subject__code=request.GET.get("subject", "math"))
    gm = load_grade(grade, get_player(request, create=False), lang)
    class_pct = None
    class_id = request.GET.get("class_id")
    if class_id:
        school_class = get_object_or_404(SchoolClass, pk=class_id)
        if not can_manage_class(request.user, school_class):
            return api_error(403, "forbidden", "Немає права переглядати статистику цього класу")
        class_pct = class_percent_map(school_class, gm)
    return ok(map_payload(gm, lang, class_pct))


def _lesson(kind: str, pk: int):
    return get_object_or_404(Item if kind == "item" else Paragraph, pk=pk)


@api_view
@require_GET
def lesson_detail(request, kind, pk):
    """Теорія уроку: блоки theory/self_check/history… (вправ тут немає)."""
    lesson = _lesson(kind, pk)
    blocks = (lesson.content_blocks.filter(block_type__in=THEORY_BLOCK_TYPES).order_by("order")
              .prefetch_related("figures"))
    title = lesson.content.splitlines()[0] if kind == "item" and lesson.content else getattr(lesson, "name_uk", "")
    return ok({"id": lesson.pk, "kind": kind, "number": lesson.number, "title": title,
               "blocks": [block_dict(b) for b in blocks]})


@api_view
@require_GET
def lesson_exercise_list(request, kind, pk):
    qs = lesson_exercises(_lesson(kind, pk))
    difficulty = request.GET.get("difficulty")
    if difficulty:
        qs = qs.filter(difficulty__in=difficulty.split(","))
    try:
        size = min(int(request.GET.get("page_size", 20)), MAX_PAGE_SIZE)
        page = Paginator(qs, max(size, 1)).page(int(request.GET.get("page", 1)))
    except (ValueError, EmptyPage) as exc:
        return api_error(400, "bad_page", str(exc))
    return ok({"count": page.paginator.count, "page": page.number, "pages": page.paginator.num_pages,
               "results": [exercise_dict(e) for e in page.object_list]})


@api_view
@require_GET
def exercise_detail(request, pk):
    ex = get_object_or_404(lesson_exercises_base(), pk=pk)
    return ok(exercise_dict(ex))


def lesson_exercises_base():
    return (Exercise.objects.filter(needs_review=False).select_related("block")
            .prefetch_related("figures", Prefetch("subexercises", queryset=SubExercise.objects.order_by("order"))))


@api_view
@require_GET
def figure_image(request, pk):
    fig = get_object_or_404(Figure, pk=pk)
    if not fig.image:
        return api_error(404, "no_image", "У рисунка немає файлу")
    return FileResponse(fig.image.open("rb"), content_type="image/png")
