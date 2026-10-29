"""Промпт і контракт відповіді для vision-LLM корекції (фаза 15).

Винесено з ``vision.py`` (BE-S12): усе, що визначає *запит* і *формат відповіді* моделі
(``PROMPT_V1``, ``RESPONSE_SCHEMA``) і перевіряє, що відповідь схемі відповідає
(``validate_response``). Клієнт/кеш/ретраї — у ``vision_client.py``, суддя/застосування
відповіді — у ``vision_response.py``.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PROMPT_VERSION = "v1"

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["text", "subitems", "confidence"],
    "additionalProperties": False,
    "properties": {
        "text": {"type": "string"},
        "subitems": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["n", "text"],
                "additionalProperties": False,
                "properties": {"n": {"type": "string"}, "text": {"type": "string"}},
            },
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}

PROMPT_V1 = """Ти — уважний коректор шкільного підручника з математики (українська мова).
На картинці — одна вправа зі сторінки. Перепиши її текст ДОСЛІВНО, нічого не розв'язуй,
нічого не додавай і не пропускай. Номер вправи і позначки складності (° • * ′) не пиши.

Правила запису математики:
- множення — «·», ділення — «:», мінус — «−», плюс — «+», дорівнює — «=»;
- звичайний дріб — «a/b» (наприклад «3/4»), мішане число — «ціле пробіл дріб» («2 1/3»);
- десятковий дріб — з комою («3,5»); степінь — «^» («10^3»);
- латинські позначення точок і відрізків (AB, MN) лишай латиницею.

Підпункти «1)», «2)», «а)» винеси в "subitems" (n — номер без дужки, text — текст підпункту);
у "text" лиши лише умову без підпунктів. Якщо підпунктів немає — "subitems": [].
"confidence" — наскільки ти впевнений, що все прочитано правильно (0..1).

Ось що прочитав звичайний OCR (може містити помилки, використовуй лише як підказку):
<<<
{ocr}
>>>

Відповідай ЛИШЕ JSON-об'єктом {{"text": ..., "subitems": [{{"n": ..., "text": ...}}], "confidence": ...}}."""

PROMPTS = {"v1": PROMPT_V1}


def validate_response(response: Any, schema: Mapping[str, Any] = RESPONSE_SCHEMA) -> str | None:
    """None — відповідь коректна; інакше текст помилки."""
    import jsonschema

    try:
        jsonschema.validate(response, schema)
    except jsonschema.ValidationError as exc:
        return exc.message
    return None
