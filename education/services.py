"""Сервіси поверх моделей підручника: що показувати в грі, перевірка відповіді, вирізки сторінок.

Тут — логіка, а views/api лише викликають її (так її легко тестувати без HTTP).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Prefetch, Q, QuerySet

from .models import Answer, ContentBlock, Exercise, Item, Paragraph, SubExercise, parse_answer_number

EXERCISE_BLOCK_TYPES = ("oral_exercise", "exercise", "review_exercise", "wise_owl", "applied_exercise")
THEORY_BLOCK_TYPES = ("theory", "self_check", "history_aside", "summary", "rule", "note", "extra_reading",
                      "worked_example", "self_test")


# --------------------------------------------------------------------------- вибірки


def lesson_blocks(lesson: Item | Paragraph) -> list[ContentBlock]:
    """Блоки уроку з вправами, підпунктами, відповідями й рисунками — фіксована кількість запитів."""
    return list(
        lesson.content_blocks.order_by("order").prefetch_related(
            "figures",
            Prefetch("exercises", queryset=Exercise.objects.order_by("order").prefetch_related(
                "figures",
                Prefetch("subexercises", queryset=SubExercise.objects.order_by("order")),
                Prefetch("answers", queryset=Answer.objects.select_related("subexercise")),
            )),
        )
    )


def playable_exercises(qs: QuerySet[Exercise] | None = None) -> QuerySet[Exercise]:
    """Вправи для гри: не позначені needs_review (політика DECISIONS: сумнівне гравцю не показуємо)."""
    qs = Exercise.objects.all() if qs is None else qs
    return qs.filter(needs_review=False)


def lesson_exercises(lesson: Item | Paragraph) -> QuerySet[Exercise]:
    field = "block__item" if isinstance(lesson, Item) else "block__paragraph"
    return (playable_exercises(Exercise.objects.filter(**{field: lesson}))
            .select_related("block").order_by("block__order", "order")
            .prefetch_related("figures", Prefetch("subexercises", queryset=SubExercise.objects.order_by("order"))))


def playable_counts(lessons: list[Item] | list[Paragraph]) -> dict[int, int]:
    """{id уроку: кількість ігрових вправ} одним запитом."""
    if not lessons:
        return {}
    field = "block__item" if isinstance(lessons[0], Item) else "block__paragraph"
    rows = (playable_exercises().filter(**{f"{field}__in": lessons})
            .values(field).annotate(n=Count("id")))
    return {r[field]: r["n"] for r in rows}


def answers_by_target(exercise: Exercise) -> dict[int | None, dict[str, str]]:
    """{id підпункту або None: {"book": "...", "computed": "..."}} (з prefetch, без зайвих запитів)."""
    result: dict[int | None, dict[str, str]] = {}
    for ans in exercise.answers.all():
        result.setdefault(ans.subexercise_id, {})[ans.kind] = ans.text
    return result


# --------------------------------------------------------------------------- перевірка відповіді

_YES = {"так", "+", "yes", "y", "та", "т"}
_NO = {"ні", "-", "no", "n", "нi"}


def normalize_answer(text: str) -> str:
    """Текстова нормалізація: регістр, пробіли, мінуси, крайні розділові знаки, так/ні."""
    value = (text or "").strip().lower().replace("−", "-").replace("–", "-").replace(" ", " ")
    value = re.sub(r"\s+", " ", value).strip(" .;!")
    value = re.sub(r"\s*;\s*", "; ", value).strip()
    if value in _YES:
        return "так"
    if value in _NO:
        return "ні"
    return value


def _join_thousands(text: str) -> str:
    """«1 454» → «1454» (пробіл між розрядами), але «2 1/3» (мішане число) не чіпаємо."""
    return re.sub(r"(?<=\d)\s(?=\d{3}(?:\D|$))(?!\d*/)", "", text)


def _parts(text: str) -> list[str]:
    return [p for p in re.split(r"\s*;\s*", normalize_answer(text)) if p]


def answers_equal(user: str, expected: str) -> bool:
    """«3,5» = «3.5» = «7/2»; «−76» = «- 76»; «Так» = «+»; «12; 16» = «12;16»."""
    exp_parts, user_parts = _parts(expected), _parts(user)
    if len(exp_parts) != len(user_parts) or not exp_parts:
        return False
    for u, e in zip(user_parts, exp_parts):
        un, en = parse_answer_number(_join_thousands(u)), parse_answer_number(_join_thousands(e))
        if un is not None and en is not None:
            if abs(un - en) > Decimal("0.000001"):
                return False
        elif normalize_answer(u) != normalize_answer(e):
            return False
    return True


@dataclass
class CheckResult:
    correct: bool
    has_answer: bool


def expected_answer(sub: SubExercise) -> str | None:
    """Пріоритет: ручна (вчитель) → книга → обчислена (лише для коректного виразу)."""
    answers = {a.kind: a.text for a in sub.answers.all()}
    for kind in ("manual", "book"):
        if kind in answers:
            return answers[kind]
    if "computed" in answers and sub.expr_status == "ok":
        return answers["computed"]
    return None


def check_answer(sub: SubExercise, user_text: str) -> CheckResult:
    expected = expected_answer(sub)
    if expected is None:
        return CheckResult(correct=False, has_answer=False)
    return CheckResult(correct=answers_equal(user_text, expected), has_answer=True)


# --------------------------------------------------------------------------- вирізка сторінки


def page_crop_png(textbook, page: int, bbox: list[int] | None, pad: int = 12) -> bytes | None:
    """PNG-вирізка сторінки PDF за bbox (для адмінки). Картинку сторінки бере з кешу пайплайна,
    а якщо її там немає — рендерить з PDF профілю. None — немає ні кешу, ні PDF."""
    import cv2

    from .pdf_pipeline.config import PipelineConfig
    from .pdf_pipeline.images import page_image_path
    from .pdf_pipeline.preprocess import load_image

    cfg = PipelineConfig.from_env_file()
    path = page_image_path(cfg.cache_dir, textbook.pdf_sha256, page)
    if not path.exists():
        from pathlib import Path

        from .pdf_pipeline.images import get_page_image
        pdf = Path(textbook.pdf_name)
        if not pdf.is_file():
            return None
        path = get_page_image(pdf, page, cfg).path
    image = load_image(path)
    if bbox:
        h, w = image.shape[:2]
        x0, y0, x1, y1 = bbox
        image = image[max(0, y0 - pad):min(h, y1 + pad), max(0, x0 - pad):min(w, x1 + pad)]
    ok, buf = cv2.imencode(".png", image)
    return buf.tobytes() if ok else None
