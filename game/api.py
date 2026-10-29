"""JSON API для гри (BE-S06: перенесено з education/api.py, docs/backend/PLAN.md).

api_error/api_view/ok/figure_dict/subexercise_dict/_lesson лишаються спільними хелперами
в education.api — education — джерело каталогу (підручники, уроки, вправи, рисунки), тому
серіалізатори вправ/рисунків і пошук уроку за kind+pk природно живуть там; крос-застосунковий
імпорт тут такий самий, як у schools/api.py.

Правила:
- GET-ендпоінти гри **ніколи не віддають відповідей**; відповідь перевіряє лише ``POST .../check/``.
- Усі помилки — ``{"error": "<код>", "detail": "<пояснення>"}`` з відповідним HTTP-статусом.
"""
from __future__ import annotations

import json
import time
from datetime import timedelta

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from education.api import _lesson, api_error, api_view, figure_dict, ok, subexercise_dict
from education.grade_map import find_lesson
from education.models import Exercise, SubExercise
from education.services import check_answer
from schools.models import SchoolMembership

from .models import LessonProgress
from .serializers import progress_dict
from .services import get_player, lesson_of, lesson_tasks, record_answer, record_solution

CHECK_LIMIT = 10           # спроб на один підпункт
CHECK_WINDOW = 60          # за стільки секунд
AI_LIMIT_PER_DAY = 5


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


@api_view
@require_POST
def check(request, pk):
    """POST {"answer": "3,5"} → {"correct", "points", "progress"}. Правильну відповідь не розкриваємо."""
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


@api_view
@require_POST
def solution(request, pk):
    """POST {"solution": "..."} → ШІ-перевірка текстової задачі (лише задачі, що є ШІ-завданнями уроку)."""
    from education.ai_check import AiUnavailable, get_ai_checker

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
    player = get_player(request, create=False)
    is_teacher = (request.user.is_authenticated
                  and SchoolMembership.objects.filter(user=request.user,
                                                      role=SchoolMembership.ROLE_TEACHER).exists())
    return ok({"authenticated": request.user.is_authenticated,
               "name": request.user.username if request.user.is_authenticated else "Гість",
               "points": player.points if player else 0, "streak": player.streak if player else 0,
               "stars": player.progress.aggregate(n=Sum("stars"))["n"] or 0 if player else 0,
               "history": _points_history(player), "is_teacher": is_teacher})
