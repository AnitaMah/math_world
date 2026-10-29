"""Серіалізатори каталогу для JSON API (BE-S07: перенесено з education/api.py).

Жодної зміни форми виводу — контракт (`static/education/mock/README.md`) той самий.
"""
from __future__ import annotations

from ..models import ContentBlock, Exercise, Figure, SubExercise


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
