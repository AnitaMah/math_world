"""Ручна перевірка (/review/): черга needs_review, застосування правок, журнал ManualEdit.

Скіп («не ігрова») лишає needs_review=True (гра такі вправи не показує) і ставить review_skipped=True
(у черзі не показується). Усі дії ставлять text_source="manual", тож import_textbook їх не перезапише.
"""
from __future__ import annotations

from collections import Counter

from django.db import transaction

from .models import Answer, Exercise, ManualEdit, SubExercise, Textbook

KINDS = ("exercise", "subexercise")


def model_for(kind: str):
    return {"exercise": Exercise, "subexercise": SubExercise}[kind]


def kind_of(obj) -> str:
    return "exercise" if isinstance(obj, Exercise) else "subexercise"


def exercise_of(obj) -> Exercise:
    return obj if isinstance(obj, Exercise) else obj.exercise


def paragraph_of(obj):
    block = exercise_of(obj).block
    return block.item.paragraph if block.item_id else block.paragraph


def text_of(obj) -> str:
    return obj.condition if isinstance(obj, Exercise) else obj.text


def apply_text(obj, new_text: str) -> None:
    """Підставляє новий текст; для обчислювальних підпунктів перераховує вираз і відповідь."""
    if isinstance(obj, Exercise):
        obj.condition = new_text
        return
    obj.text = new_text
    exercise = obj.exercise
    if exercise.task_verb != "compute":
        return
    from education.pdf_pipeline.content.math_text import analyze_expression
    result = analyze_expression(new_text, natural_numbers=exercise.textbook.grade.number <= 5)
    obj.expr, obj.expr_status, obj.expr_issues = result.expression, result.status, result.issues
    Answer.objects.filter(exercise=exercise, subexercise=obj, kind="computed").delete()
    computed = None
    if result.answer is not None:
        computed = Answer.objects.create(exercise=exercise, subexercise=obj, kind="computed", text=result.answer)
    book = Answer.objects.filter(exercise=exercise, subexercise=obj, kind="book").first()
    if book is not None and computed is not None:
        obj.answer_check = "verified" if book.value_numeric == computed.value_numeric else "mismatch"


def _journal(user, obj, action, old="", new=""):
    ex = exercise_of(obj)
    return ManualEdit.objects.create(
        user=user if getattr(user, "is_authenticated", False) else None,
        action=action, textbook=ex.textbook, kind=kind_of(obj), block_type=ex.block.block_type,
        exercise_number=ex.number, source_page=ex.source_page,
        sub_number=obj.number if isinstance(obj, SubExercise) else "", old_text=old, new_text=new)


@transaction.atomic
def save_edit(obj, new_text: str, user=None) -> str:
    """Зберігає текст. Якщо він не змінився — це «підтверджено». Повертає дію (edit/confirm)."""
    new_text = new_text.strip()
    old = text_of(obj)
    action = "edit" if new_text and new_text != old else "confirm"
    if action == "edit":
        apply_text(obj, new_text)
    obj.text_source, obj.needs_review, obj.review_skipped = "manual", False, False
    obj.save()
    _journal(user, obj, action, old, text_of(obj))
    return action


@transaction.atomic
def skip(obj, user=None) -> None:
    obj.text_source, obj.needs_review, obj.review_skipped = "manual", True, True
    obj.save()
    _journal(user, obj, "skip", text_of(obj), text_of(obj))


@transaction.atomic
def unskip(obj, user=None) -> None:
    obj.review_skipped, obj.needs_review = False, True
    obj.save()
    _journal(user, obj, "unskip", text_of(obj), text_of(obj))


def queue(textbook=None, paragraph_id=None, kind=None, skipped=False):
    """Список (kind, obj) у порядку сторінок. skipped=True — показати лише пропущені."""
    items = []
    if kind in (None, "", "exercise"):
        qs = Exercise.objects.filter(needs_review=True, review_skipped=skipped)
        if textbook:
            qs = qs.filter(textbook=textbook)
        items += [("exercise", o) for o in qs.select_related("textbook", "block__item__paragraph", "block__paragraph")]
    if kind in (None, "", "subexercise"):
        qs = SubExercise.objects.filter(needs_review=True, review_skipped=skipped)
        if not skipped:
            qs = qs.filter(exercise__review_skipped=False)
        if textbook:
            qs = qs.filter(exercise__textbook=textbook)
        items += [("subexercise", o) for o in qs.select_related(
            "exercise__textbook", "exercise__block__item__paragraph", "exercise__block__paragraph")]
    if paragraph_id:
        items = [(k, o) for k, o in items if paragraph_of(o).pk == int(paragraph_id)]
    items.sort(key=lambda ko: (exercise_of(ko[1]).textbook_id, exercise_of(ko[1]).source_page or 0,
                               exercise_of(ko[1]).order, ko[0] != "exercise",
                               getattr(ko[1], "order", 0)))
    return items


def counters(textbook=None):
    """[(paragraph, залишилось)] — скільки елементів черги лишилось у кожному §."""
    cnt, paragraphs = Counter(), {}
    for _, obj in queue(textbook):
        p = paragraph_of(obj)
        cnt[p.pk] += 1
        paragraphs[p.pk] = p
    return sorted(((paragraphs[pk], n) for pk, n in cnt.items()), key=lambda t: (t[0].section_id, t[0].number))


def find_object(textbook, kind, block_type, number, page, sub_number=""):
    qs = Exercise.objects.filter(textbook=textbook, number=number, block__block_type=block_type)
    if page is not None:
        qs = qs.filter(source_page=page)
    ex = qs.order_by("pk").first()
    if ex is None:
        return None
    if kind == "exercise":
        return ex
    return ex.subexercises.filter(number=sub_number).first()
