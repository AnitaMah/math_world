"""Перевіряє, що моки відповідають контракту з бекендом (обов’язкові поля й типи).

Запуск: python tools/frontend/check_mocks.py — друкує помилки, код виходу 1, якщо є.
Те саме викликає education.tests_ui.MockContractTests.
"""
import json
import sys
from pathlib import Path

MOCK = Path(__file__).resolve().parents[2] / "education" / "static" / "education" / "mock"
STATES = {"done", "current", "open", "locked", "soon"}
BLOCKS = {"theory", "self_check", "oral_exercise", "exercise", "review_exercise", "wise_owl", "history_aside"}


def _lesson(lesson, where, errors):
    need = {"id": int, "number": int, "title": str, "state": str, "stars": int, "solved": int, "total": int,
            "tasks": dict, "blocks": list, "map": dict}
    for key, typ in need.items():
        if not isinstance(lesson.get(key), typ) or (typ is int and isinstance(lesson.get(key), bool)):
            errors.append(f"{where}: поле `{key}` має бути {typ.__name__}")
    if lesson.get("state") not in STATES:
        errors.append(f"{where}: state={lesson.get('state')!r} — не з {sorted(STATES)}")
    if not 0 <= lesson.get("stars", -1) <= 3:
        errors.append(f"{where}: stars поза 0–3")
    tasks = lesson.get("tasks") or {}
    if set(tasks) != {"auto", "ai"}:
        errors.append(f"{where}: tasks має бути {{auto, ai}}")
    elif tasks["auto"] + tasks["ai"] != lesson.get("total"):
        errors.append(f"{where}: total ≠ auto + ai")
    if lesson.get("solved", 0) > lesson.get("total", 0):
        errors.append(f"{where}: solved > total")
    if lesson.get("total") == 0 and lesson.get("state") != "soon":
        errors.append(f"{where}: урок без завдань має бути `soon`")
    if set(lesson.get("blocks", [])) - BLOCKS:
        errors.append(f"{where}: невідомі blocks {set(lesson['blocks']) - BLOCKS}")
    if set(lesson.get("map") or {}) != {"x", "y"}:
        errors.append(f"{where}: map має бути {{x, y}}")


def check_grade_map(data, name):
    errors = []
    for key in ("grade", "subject", "textbook", "current", "sections"):
        if key not in data:
            errors.append(f"{name}: немає `{key}`")
    for s in data.get("sections", []):
        for key in ("id", "number", "title", "paragraphs"):
            if key not in s:
                errors.append(f"{name} розділ {s.get('number')}: немає `{key}`")
        for p in s.get("paragraphs", []):
            where = f"{name} §{p.get('number')}"
            for key in ("id", "number", "title", "items"):
                if key not in p:
                    errors.append(f"{where}: немає `{key}`")
            if p.get("items"):
                for it in p["items"]:
                    _lesson(it, f"{where} урок {it.get('number')}", errors)
            else:  # Тарасенкова: урок = §
                _lesson(p, f"{where} (урок = §)", errors)
    cur = data.get("current")
    if cur is not None and set(cur) != {"kind", "id"}:
        errors.append(f"{name}: current має бути {{kind, id}} або null")
    return errors


def check_all():
    errors = []
    for path in sorted(MOCK.glob("grade-*.json")):
        errors += check_grade_map(json.loads(path.read_text(encoding="utf-8")), path.name)
    grades = json.loads((MOCK / "grades.json").read_text(encoding="utf-8"))
    for g in grades:
        for key in ("number", "subject", "author", "year", "sections", "lessons", "playable_lessons",
                    "stars", "max_stars", "current"):
            if key not in g:
                errors.append(f"grades.json клас {g.get('number')}: немає `{key}`")
    for name in ("me.guest.json", "me.user.json"):
        me = json.loads((MOCK / name).read_text(encoding="utf-8"))
        for key in ("authenticated", "name", "points", "streak", "stars"):
            if key not in me:
                errors.append(f"{name}: немає `{key}`")
    return errors


if __name__ == "__main__":
    problems = check_all()
    print("\n".join(problems) if problems else "Моки відповідають контракту.")
    sys.exit(1 if problems else 0)
