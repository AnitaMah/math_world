"""Перевірка і застосування відповіді vision-LLM (фаза 15).

Винесено з ``vision.py`` (BE-S12). Відповідь моделі **не довіряємо сліпо**:

1. невалідний JSON / не та схема → не застосовуємо;
2. відповідь у 2+ рази довша за OCR → модель, мабуть, «дописала» → відкидаємо;
3. CER між OCR і LLM > 50 % → надто різні тексти, автоматично не застосовуємо (лише у звіт);
4. номери підпунктів не збіглися з OCR → текст застосовуємо, але лишаємо ``needs_review``.

Обидві версії зберігаються: ``data['ocr_text']``, ``data['vision_text']``, ``data['text_source']``.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .bench import cer
from .datatypes import Node
from .vision_prompts import validate_response
from .vision_targets import _written_subitems, exercise_ocr_text

MAX_LENGTH_RATIO = 2.0
MAX_AUTO_CER = 0.5
MIN_LENGTH_BASE = 20          # для дуже коротких OCR-текстів порівнюємо з 20 символами


def _canon_apostrophes(text: str) -> str:
    """Модель повертає типографський апостроф («від’ємник»); у проєкті він один (як після normalize)."""
    from .normalize import APOSTROPHES, CANON_APOSTROPHE
    return "".join(CANON_APOSTROPHE if ch in APOSTROPHES else ch for ch in text)


def vision_full_text(response: Mapping[str, Any]) -> str:
    lines = [response.get("text", "")] + [f"{s['n']}) {s['text']}" for s in response.get("subitems", [])]
    return "\n".join(line for line in lines if line)


@dataclass
class Decision:
    status: str               # applied | applied_review | rejected_length | rejected_cer | invalid
    reason: str = ""
    cer: float | None = None


def judge(ocr_text: str, response: Any, ocr_labels: Sequence[str]) -> Decision:
    """Захист від галюцинацій (кроки 0656–0659)."""
    error = validate_response(response)
    if error:
        return Decision("invalid", f"схема: {error}")
    llm_text = vision_full_text(response)
    if len(llm_text) > MAX_LENGTH_RATIO * max(len(ocr_text), MIN_LENGTH_BASE):
        return Decision("rejected_length", f"{len(llm_text)} символів проти {len(ocr_text)} в OCR")
    distance = cer(ocr_text, llm_text)
    if distance > MAX_AUTO_CER:
        return Decision("rejected_cer", f"CER {distance:.0%}", distance)
    llm_labels = [s["n"].strip().rstrip(")") for s in response["subitems"]]
    if list(ocr_labels) != llm_labels:
        return Decision("applied_review", f"підпункти OCR {list(ocr_labels)} ≠ LLM {llm_labels}", distance)
    return Decision("applied", "", distance)


def apply_response(ex: Node, response: Mapping[str, Any], decision: Decision,
                   natural_numbers: bool = True) -> None:
    """Записує результат у вправу. Обидві версії тексту лишаються в data."""
    from .math_text import analyze_expression

    ocr_text = exercise_ocr_text(ex)
    ex.data["ocr_text"] = ocr_text
    ex.data["vision_status"] = decision.status
    if decision.reason:
        ex.data["vision_reason"] = decision.reason
    if decision.cer is not None:
        ex.data["vision_cer"] = round(decision.cer, 3)
    if decision.status in ("invalid",):
        ex.data["text_source"] = "ocr"
        return
    ex.data["vision_text"] = vision_full_text(response)
    ex.data["vision_confidence"] = response.get("confidence")
    if not decision.status.startswith("applied"):
        ex.data["text_source"] = "ocr"          # лише у звіт, людина вирішить
        ex.needs_review = True
        return

    ex.data["text_source"] = "vision"
    ex.data["condition"] = _canon_apostrophes(response["text"].strip())
    subs = {s.number: s for s in _written_subitems(ex)}
    compute = ex.data.get("task_verb") == "compute"
    for item in response["subitems"]:
        label = item["n"].strip().rstrip(")")
        sub = subs.get(label)
        if sub is None:
            continue
        sub.data["ocr_text"] = sub.text
        sub.text = _canon_apostrophes(item["text"].strip())
        sub.data["text_source"] = "vision"
        if compute:
            result = analyze_expression(sub.text, natural_numbers=natural_numbers)
            sub.data.update(expr=result.expression, expr_status=result.status)
            sub.data.pop("expr_issues", None)
            sub.data.pop("answer", None)
            if result.issues:
                sub.data["expr_issues"] = result.issues
            if result.answer is not None:
                sub.data.update(answer=result.answer, answer_source="computed")
            sub.needs_review = result.status in ("suspect", "malformed")
        else:
            sub.needs_review = False
    if decision.status == "applied":
        ex.needs_review = any(s.needs_review for s in _written_subitems(ex))
    else:
        ex.needs_review = True
