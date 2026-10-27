"""JSON API для гри (фаза 21). Прості ``JsonResponse`` без DRF — рішення в DECISIONS.md.

Правила:
- GET-ендпоінти гри **ніколи не віддають відповідей**; відповідь перевіряє лише ``POST .../check/``.
- Вправи з ``needs_review`` у гру не потрапляють (404 для однієї вправи, відфільтровані в списках).
- Усі помилки — ``{"error": "<код>", "detail": "<пояснення>"}`` з відповідним HTTP-статусом.
"""
from __future__ import annotations

import functools
import json
import time
from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import EmptyPage, Paginator
from django.db.models import Prefetch, Sum
from django.db.models.functions import TruncDate
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import ContentBlock, Exercise, Figure, Grade, Item, Paragraph, Section, SubExercise, Textbook
from .services import THEORY_BLOCK_TYPES, check_answer, lesson_exercises, playable_counts

CHECK_LIMIT = 10           # спроб на один підпункт
CHECK_WINDOW = 60          # за стільки секунд
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


# --------------------------------------------------------------------------- серіалізатори (без відповідей!)


def figure_dict(fig: Figure) -> dict:
    return {"id": fig.pk, "number": fig.number, "caption": fig.caption,
            "url": f"/api/figures/{fig.pk}/image" if fig.image else None}


def subexercise_dict(sub: SubExercise) -> dict:
    return {"id": sub.pk, "number": sub.number, "text": sub.text}


def exercise_dict(ex: Exercise) -> dict:
    return {"id": ex.pk, "number": ex.number, "difficulty": ex.difficulty, "block_type": ex.block.block_type,
            "condition": ex.condition, "condition_tail": ex.condition_tail, "homework": ex.homework,
            "auto_checkable": ex.auto_checkable,
            # підпункти needs_review теж не показуємо (напр. сумнівна мітка «1)» замість «5)»)
            "subexercises": [subexercise_dict(s) for s in ex.subexercises.all() if not s.needs_review],
            "figures": [figure_dict(f) for f in ex.figures.all()]}


def block_dict(block: ContentBlock) -> dict:
    return {"id": block.pk, "type": block.block_type, "title": block.title, "text": block.text,
            "figures": [figure_dict(f) for f in block.figures.all()]}


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
    from .game import get_player
    from .grade_map import grade_summary, load_grade

    player = get_player(request, create=False)
    qs = Grade.objects.filter(subject__code=request.GET.get("subject", "math")).order_by("number")
    return ok([grade_summary(gm) for gm in (load_grade(g, player) for g in qs) if gm.sections])


@api_view
@require_GET
def grade_map(request, number):
    """Мапа класу (контракт `docs/frontend`): розділи → § → уроки зі станом, зірками, завданнями, блоками."""
    from .game import get_player
    from .grade_map import load_grade, map_payload

    grade = get_object_or_404(Grade, number=number, subject__code=request.GET.get("subject", "math"))
    return ok(map_payload(load_grade(grade, get_player(request, create=False))))


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


def _rate_limited(request, key: str, limit: int = CHECK_LIMIT, window: int = CHECK_WINDOW) -> bool:
    now = time.time()
    attempts = request.session.get("check_attempts", {})
    recent = [t for t in attempts.get(key, []) if now - t < window]
    if len(recent) >= limit:
        return True
    attempts[key] = recent + [now]
    request.session["check_attempts"] = attempts
    return False


def _payload_text(request, field: str, max_len: int):
    try:
        payload = json.loads(request.body or b"{}") if request.content_type == "application/json" else request.POST
    except ValueError:
        return None, api_error(400, "bad_json", "Тіло запиту — не JSON")
    text = (payload.get(field) or "").strip()
    if not text:
        return None, api_error(400, f"empty_{field}", "Порожня відповідь")
    if len(text) > max_len:
        return None, api_error(400, f"{field}_too_long", "Задовго")
    return text, None


def progress_dict(prog) -> dict | None:
    if prog is None:
        return None
    return {"solved": prog.solved, "total": prog.total, "points": prog.points, "stars": prog.stars}


@api_view
@require_POST
def check(request, pk):
    """POST {"answer": "3,5"} → {"correct", "points", "progress"}. Правильну відповідь не розкриваємо."""
    from .game import get_player, record_answer

    sub = get_object_or_404(SubExercise.objects.select_related("exercise__block").prefetch_related("answers"),
                            pk=pk, needs_review=False, exercise__needs_review=False)
    answer, error = _payload_text(request, "answer", 200)
    if error:
        return error
    if _rate_limited(request, str(pk)):
        return api_error(429, "too_many_attempts", f"Не більше {CHECK_LIMIT} спроб на хвилину")
    result = check_answer(sub, answer)
    if not result.has_answer:
        return api_error(409, "no_answer", "Для цього підпункту немає відповіді для перевірки")
    player = get_player(request)
    res = record_answer(player, sub, answer)
    return ok({"subexercise": sub.pk, "correct": res.correct, "points": res.points,
               "already_solved": res.already_solved, "total_points": player.points, "streak": player.streak,
               "progress": progress_dict(res.progress)})


AI_LIMIT_PER_DAY = 5


@api_view
@require_POST
def solution(request, pk):
    """POST {"solution": "..."} → ШІ-перевірка текстової задачі (лише задачі, що є ШІ-завданнями уроку)."""
    from .ai_check import AiUnavailable, get_ai_checker
    from .game import get_player, lesson_of, lesson_tasks, record_solution

    ex = get_object_or_404(Exercise.objects.select_related("block", "textbook__grade"), pk=pk, needs_review=False)
    if f"e{ex.pk}" not in {t.id for t in lesson_tasks(lesson_of(ex))}:
        return api_error(400, "not_ai_task", "Ця вправа не перевіряється ШІ")
    text, error = _payload_text(request, "solution", 1500)
    if error:
        return error
    if _rate_limited(request, f"ai{pk}", AI_LIMIT_PER_DAY, 24 * 3600):
        return api_error(429, "too_many_attempts", f"Не більше {AI_LIMIT_PER_DAY} перевірок ШІ на задачу за добу")
    checker = get_ai_checker()
    if checker is None:
        return api_error(503, "ai_unavailable", "Перевірка ШІ не налаштована (немає GEMINI_API_KEY)")
    try:
        res = record_solution(get_player(request), ex, text, checker)
    except Exception as exc:  # noqa: BLE001 — мережа/бюджет/формат: гравцю — зрозуміла помилка
        detail = str(exc) if isinstance(exc, AiUnavailable) else "ШІ зараз недоступний, спробуй пізніше"
        return api_error(503, "ai_unavailable", detail)
    return ok({"exercise": ex.pk, "correct": res.correct, "verdict": res.verdict, "feedback": res.feedback,
               "points": res.points, "already_solved": res.already_solved, "progress": progress_dict(res.progress)})


@api_view
@require_GET
def play(request, kind, pk):
    """Усі завдання уроку для екрана гри (без відповідей) + прогрес поточного гравця."""
    from .game import get_player, lesson_tasks
    from .models import LessonProgress

    from .grade_map import find_lesson

    lesson = _lesson(kind, pk)
    player = get_player(request, create=False)
    gm, info = find_lesson(kind, lesson, player)
    if info.state == "locked" and not request.user.is_staff:
        return api_error(403, "lesson_locked", "Спершу пройди попередній урок")
    tasks = lesson_tasks(lesson, player)
    lookup = {"item": lesson} if kind == "item" else {"paragraph": lesson}
    prog = LessonProgress.objects.filter(player=player, **lookup).first() if player else None
    title = lesson.content.splitlines()[0] if kind == "item" and lesson.content else getattr(lesson, "name_uk", "")
    return ok({
        "lesson": {"id": lesson.pk, "kind": kind, "number": lesson.number, "title": title,
                   "grade": gm.grade.number, "section_number": info.section.number,
                   "paragraph_number": info.paragraph.number, "island": gm.paragraph_island[info.paragraph.pk],
                   "state": info.state},
        "tasks": [{"id": t.id, "kind": t.kind, "points": t.points, "solved": t.solved,
                   "exercise": {"id": t.exercise.pk, "number": t.exercise.number, "difficulty": t.exercise.difficulty,
                                "condition": t.exercise.condition, "condition_tail": t.exercise.condition_tail,
                                "figures": [figure_dict(f) for f in t.exercise.figures.all()]},
                   "sub": subexercise_dict(t.sub) if t.sub else None} for t in tasks],
        "progress": progress_dict(prog),
    })


def _points_history(player) -> list[dict]:
    """Бали гравця за кожен з останніх 7 днів (найстаріший → сьогодні), для екрана «Прогрес»."""
    today = timezone.localdate()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    totals = dict.fromkeys(days, 0)
    if player is not None:
        rows = (player.attempts.filter(created_at__date__gte=days[0])
                .annotate(day=TruncDate("created_at")).values("day").annotate(n=Sum("points")))
        for row in rows:
            if row["day"] in totals:
                totals[row["day"]] = row["n"] or 0
    return [{"date": d.isoformat(), "points": totals[d]} for d in days]


@api_view
@require_GET
def me(request):
    from .game import get_player
    player = get_player(request, create=False)
    return ok({"authenticated": request.user.is_authenticated,
               "name": request.user.username if request.user.is_authenticated else "Гість",
               "points": player.points if player else 0, "streak": player.streak if player else 0,
               "stars": player.progress.aggregate(n=Sum("stars"))["n"] or 0 if player else 0,
               "history": _points_history(player)})
