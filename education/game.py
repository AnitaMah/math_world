"""Ігрова логіка (фаза 21Б): гравець, завдання уроку, бали, зірки, серія днів.

Правила — DECISIONS.md «ігрова механіка». Тут лише сервіси; views/api їх викликають.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from .models import (
    DIFFICULTY_POINTS, Answer, Attempt, Exercise, Item, LessonProgress, Paragraph, Player, SubExercise,
)
from .services import answers_equal, expected_answer

AI_TASKS_PER_LESSON = 3
FULL_POINTS_ATTEMPTS = 2           # з 1-ї–2-ї спроби — повні бали, далі — половина
STAR_THRESHOLDS = (0.3, 0.7, 1.0)

# --------------------------------------------------------------------------- гравець


def get_player(request, create: bool = True) -> Player | None:
    """Гравець поточного запиту: акаунт або анонім сесії."""
    if request.user.is_authenticated:
        if create:
            return Player.objects.get_or_create(user=request.user)[0]
        return Player.objects.filter(user=request.user).first()
    if not request.session.session_key:
        if not create:
            return None
        request.session.save()
    key = request.session.session_key
    if not create:
        return Player.objects.filter(session_key=key).first()
    player = Player.objects.get_or_create(session_key=key)[0]
    # id гравця в даних сесії: login() міняє ключ сесії (cycle_key), але дані зберігає
    request.session["player_id"] = player.pk
    return player


@transaction.atomic
def merge_players(source: Player, target: Player) -> None:
    """Переносить прогрес аноніма в акаунт: спроби — усі, бали — сума, зірки — максимум."""
    if source.pk == target.pk:
        return
    source.attempts.update(player=target)
    for prog in source.progress.all():
        lookup = {"item": prog.item} if prog.item_id else {"paragraph": prog.paragraph}
        mine = target.progress.filter(**lookup).first()
        if mine is None:
            prog.player = target
            prog.save()
        else:
            mine.stars = max(mine.stars, prog.stars)
            mine.save()
            prog.delete()
    target.points += source.points
    target.streak = max(target.streak, source.streak)
    target.last_active = max(filter(None, [target.last_active, source.last_active]), default=None)
    target.save()
    source.delete()
    for prog in target.progress.all():
        recompute_progress(target, prog.item or prog.paragraph)


def on_login(sender, request, user, **kwargs):
    """Сигнал user_logged_in: анонімний прогрес цієї сесії → акаунт.

    Шукаємо за ``player_id`` у даних сесії, бо до цього моменту login() уже змінив ключ сесії."""
    pid = request.session.get("player_id") if request is not None else None
    anon = Player.objects.filter(pk=pid, user__isnull=True).first() if pid else None
    if anon is not None:
        account = Player.objects.get_or_create(user=user)[0]
        merge_players(anon, account)
        request.session["player_id"] = account.pk


# --------------------------------------------------------------------------- завдання уроку


@dataclass
class Task:
    id: str                         # "s<id підпункту>" або "e<id вправи>"
    kind: str                       # auto | ai
    exercise: Exercise
    sub: SubExercise | None = None
    points: int = 1
    solved: bool = False


def exercise_points(ex: Exercise) -> int:
    return DIFFICULTY_POINTS.get(ex.difficulty or "", 1)


def _lesson_filter(lesson) -> dict:
    return {"block__item": lesson} if isinstance(lesson, Item) else {"block__paragraph": lesson}


def lesson_tasks(lesson, player: Player | None = None) -> list[Task]:
    """Завдання уроку в порядку книги: авто-підпункти + до 3 ШІ-задач. needs_review — ні."""
    exercises = (Exercise.objects.filter(needs_review=False, **_lesson_filter(lesson))
                 .select_related("block").order_by("block__order", "order")
                 .prefetch_related("figures",
                                   Prefetch("subexercises", queryset=SubExercise.objects.filter(needs_review=False)
                                            .order_by("order").prefetch_related("answers")),
                                   "answers"))
    tasks: list[Task] = []
    ai_left = AI_TASKS_PER_LESSON
    for ex in exercises:
        auto = [Task(f"s{s.pk}", "auto", ex, s, exercise_points(ex)) for s in ex.subexercises.all()
                if expected_answer(s) is not None]
        if auto:
            tasks += auto
        elif ex.is_word_problem and ai_left > 0:
            tasks.append(Task(f"e{ex.pk}", "ai", ex, None, exercise_points(ex) * 2))
            ai_left -= 1
    if player is not None and tasks:
        solved = set(Attempt.objects.filter(player=player, correct=True, exercise__in={t.exercise for t in tasks})
                     .values_list("subexercise_id", "exercise_id"))
        for t in tasks:
            t.solved = (t.sub.pk if t.sub else None, t.exercise.pk) in solved
    return tasks


def lesson_of(exercise: Exercise):
    return exercise.block.item or exercise.block.paragraph


# --------------------------------------------------------------------------- бали і прогрес


def stars_for(solved: int, total: int) -> int:
    if not total:
        return 0
    share = solved / total
    return sum(share >= t - 1e-9 for t in STAR_THRESHOLDS)


def recompute_progress(player: Player, lesson) -> LessonProgress:
    tasks = lesson_tasks(lesson, player)
    lookup = {"item": lesson} if isinstance(lesson, Item) else {"paragraph": lesson}
    prog, _ = LessonProgress.objects.get_or_create(player=player, **lookup)
    ids = [t.exercise.pk for t in tasks]
    prog.total = len(tasks)
    prog.solved = sum(t.solved for t in tasks)
    prog.points = sum(Attempt.objects.filter(player=player, exercise_id__in=ids).values_list("points", flat=True))
    prog.stars = max(prog.stars, stars_for(prog.solved, prog.total))      # зірки не відбираємо
    prog.save()
    return prog


def _touch_streak(player: Player) -> None:
    today = timezone.localdate()
    if player.last_active == today:
        return
    player.streak = player.streak + 1 if player.last_active == today - timedelta(days=1) else 1
    player.last_active = today


@dataclass
class AttemptResult:
    correct: bool
    points: int = 0
    already_solved: bool = False
    verdict: str = ""
    feedback: str = ""
    progress: LessonProgress | None = None
    extra: dict = field(default_factory=dict)


def _award(player: Player, ex: Exercise, sub: SubExercise | None, correct: bool, base: int) -> tuple[int, bool]:
    prev = Attempt.objects.filter(player=player, exercise=ex, subexercise=sub)
    if prev.filter(correct=True).exists():
        return 0, True
    if not correct:
        return 0, False
    tries = prev.count() + 1
    return (base if tries <= FULL_POINTS_ATTEMPTS else max(1, base // 2)), False


@transaction.atomic
def record_answer(player: Player, sub: SubExercise, text: str) -> AttemptResult:
    expected = expected_answer(sub)
    correct = expected is not None and answers_equal(text, expected)
    ex = sub.exercise
    points, already = _award(player, ex, sub, correct, exercise_points(ex))
    Attempt.objects.create(player=player, exercise=ex, subexercise=sub, kind="auto", answer_text=text[:500],
                           correct=correct, points=points)
    return _finish(player, ex, AttemptResult(correct, points, already), correct)


@transaction.atomic
def record_solution(player: Player, ex: Exercise, text: str, checker) -> AttemptResult:
    task = ex.condition + "".join(f"\n{s.number}) {s.text}" for s in ex.subexercises.all())
    book = Answer.objects.filter(exercise=ex, subexercise__isnull=True, kind__in=("manual", "book")).first()
    verdict = checker.check(task, text, ex.textbook.grade.number, book.text if book else None)
    correct = verdict.verdict == "correct"
    points, already = _award(player, ex, None, correct, exercise_points(ex) * 2)
    Attempt.objects.create(player=player, exercise=ex, kind="ai", answer_text=text[:2000], correct=correct,
                           verdict=verdict.verdict, feedback=verdict.feedback, points=points)
    return _finish(player, ex, AttemptResult(correct, points, already, verdict.verdict, verdict.feedback), correct)


def _finish(player: Player, ex: Exercise, result: AttemptResult, correct: bool) -> AttemptResult:
    if correct:
        player.points += result.points
        _touch_streak(player)
        player.save()
    result.progress = recompute_progress(player, lesson_of(ex))
    return result
