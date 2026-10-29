"""JSON-контракт між пайплайном і бекендом (фаза 16).

Пайплайн усередині працює з деревом ``Node`` (гнучким, з будь-якими ``data``).
Назовні віддаємо **стабільний** формат, описаний тут JSON Schema. Бекенд-імпортер
(фаза 19) читає лише його, тож внутрішні зміни пайплайну не ламають базу.

Правила версіонування: будь-яка несумісна зміна (перейменування/видалення поля,
нове обов'язкове поле) → ``SCHEMA_VERSION += 1`` і запис у DECISIONS.md.
Нові необов'язкові поля версію не змінюють.
"""
from __future__ import annotations

from typing import Any

from ..profiles import BLOCK_TYPES, DIFFICULTY_LEVELS

SCHEMA_VERSION = 1

_STR = {"type": "string"}
_NSTR = {"type": ["string", "null"]}
_BOOL = {"type": "boolean"}
_INT = {"type": "integer"}
_NUM_N = {"type": ["number", "null"]}
_STRS = {"type": "array", "items": _STR}


def _obj(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "required": required, "additionalProperties": False, "properties": properties}


DEFINITIONS: dict[str, Any] = {
    "source": _obj(["pdf_page"], {
        "pdf_page": {"type": "integer", "minimum": 1},
        "book_page": {"type": ["integer", "null"]},
        "bbox": {"oneOf": [{"type": "null"},
                           {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}]},
    }),
    "nullable_source": {"oneOf": [{"type": "null"}, {"$ref": "#/definitions/source"}]},
    "text_source": {"enum": ["ocr", "vision", "manual"]},
    "difficulty": {"enum": [*DIFFICULTY_LEVELS, "unknown", None]},
    "answer": _obj([], {
        "computed": _NSTR,          # обчислено пайплайном (math_text)
        "book": _NSTR,              # з розділу «Відповіді» книги
        "verified": _BOOL,          # computed == book
        "mismatch": _BOOL,          # computed != book
    }),
    "figure": _obj(["id", "number", "path", "source"], {
        "id": _STR, "number": _NSTR, "title": _STR, "path": _NSTR,
        "source": {"$ref": "#/definitions/source"},
    }),
    "subexercise": _obj(["number", "text", "needs_review"], {
        "number": _STR, "text": _STR,
        "raw_label": _NSTR, "label_fixed": _BOOL,
        "expr": _NSTR,
        "expr_status": {"enum": ["ok", "suspect", "malformed", "not_expression", None]},
        "expr_issues": _STRS,
        "answer": {"$ref": "#/definitions/answer"},
        "text_source": {"$ref": "#/definitions/text_source"},
        "ocr_text": _NSTR,
        "needs_review": _BOOL,
    }),
    "exercise": _obj(["number", "difficulty", "condition", "subexercises", "needs_review", "source"], {
        "number": _STR,
        "difficulty": {"$ref": "#/definitions/difficulty"},
        "difficulty_ocr": _NSTR,
        "homework": _BOOL,
        "condition": _STR,
        "condition_tail": _STR,
        "task_verb": _NSTR, "answer_kind": _NSTR,
        "is_word_problem": _BOOL, "auto_checkable": _BOOL, "has_fractions": _BOOL,
        "subexercises": {"type": "array", "items": {"$ref": "#/definitions/subexercise"}},
        "answer": {"$ref": "#/definitions/answer"},
        "book_answer_parts": {"type": "object", "additionalProperties": _STR},
        "figure_ids": _STRS, "figure_refs": _STRS, "missing_figures": _STRS,
        "text_source": {"$ref": "#/definitions/text_source"},
        "ocr_text": _NSTR, "vision_text": _NSTR, "vision_status": _NSTR, "vision_reason": _NSTR,
        "flags": _STRS,
        "needs_review": _BOOL,
        "source": {"$ref": "#/definitions/nullable_source"},
    }),
    "block": _obj(["type", "text", "exercises", "figure_ids", "needs_review"], {
        "type": {"enum": sorted(BLOCK_TYPES)},
        "title": _STR, "text": _STR,
        "exercises": {"type": "array", "items": {"$ref": "#/definitions/exercise"}},
        "figure_ids": _STRS,
        "needs_review": _BOOL,
        "source": {"$ref": "#/definitions/nullable_source"},
    }),
    "item": _obj(["number", "title", "blocks"], {
        "number": _STR, "title": _STR, "ocr_title": _NSTR,
        "blocks": {"type": "array", "items": {"$ref": "#/definitions/block"}},
        "figure_ids": _STRS,
        "source": {"$ref": "#/definitions/nullable_source"},
    }),
    "paragraph": _obj(["number", "title", "items", "blocks"], {
        "number": _STR, "title": _STR, "ocr_title": _NSTR,
        "items": {"type": "array", "items": {"$ref": "#/definitions/item"}},
        "blocks": {"type": "array", "items": {"$ref": "#/definitions/block"}},   # Тарасенкова: урок = §; Мерзляк: «Перевірте себе»
        "figure_ids": _STRS,
        "source": {"$ref": "#/definitions/nullable_source"},
    }),
    "section": _obj(["number", "title", "paragraphs"], {
        "number": _STR, "title": _STR, "index": {"type": ["integer", "null"]},
        "paragraphs": {"type": "array", "items": {"$ref": "#/definitions/paragraph"}},
        "source": {"$ref": "#/definitions/nullable_source"},
    }),
    "problem": _obj(["code", "severity", "message"], {
        "code": _STR, "severity": {"enum": ["error", "warning", "info"]}, "message": _STR,
        "source": {"$ref": "#/definitions/nullable_source"}, "node_path": _STR, "text": _STR,
        "data": {"type": "object"},
    }),
}

TEXTBOOK_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "math_world textbook export",
    **_obj(["schema_version", "pipeline_version", "meta", "stats", "sections", "figures", "problems"], {
        "schema_version": {"const": SCHEMA_VERSION},
        "pipeline_version": _STR,
        "meta": _obj(["profile", "subject", "grade", "title", "pdf_name", "pdf_sha256", "created_at"], {
            "profile": _STR, "subject": _STR, "grade": _INT, "title": _STR,
            "pdf_name": _STR, "pdf_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "created_at": _STR, "pages": {"type": "array", "items": _INT},
        }),
        "stats": {"type": "object", "additionalProperties": _INT},
        "sections": {"type": "array", "items": {"$ref": "#/definitions/section"}},
        "figures": {"type": "array", "items": {"$ref": "#/definitions/figure"}},
        "problems": {"type": "array", "items": {"$ref": "#/definitions/problem"}},
    }),
    "definitions": DEFINITIONS,
}


class SchemaError(ValueError):
    """Експорт не відповідає схемі або схема іншої версії."""


def validate_textbook(data: Any) -> None:
    """Кидає SchemaError з шляхом до першої проблеми."""
    import jsonschema

    validator = jsonschema.Draft7Validator(TEXTBOOK_SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.absolute_path) or "<корінь>"
        raise SchemaError(f"{where}: {first.message} (усього помилок: {len(errors)})")
