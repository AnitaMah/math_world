"""Серіалізатори гри для JSON API (BE-S08: перенесено з game/api.py).

Жодної зміни форми виводу — контракт (`static/education/mock/README.md`) той самий.
"""
from __future__ import annotations


def progress_dict(prog) -> dict | None:
    if prog is None:
        return None
    return {"solved": prog.solved, "total": prog.total, "points": prog.points, "stars": prog.stars}
