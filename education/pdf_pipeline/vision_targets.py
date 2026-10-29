"""Вибір зон для vision-LLM (фаза 15): які вправи варто показати моделі і підготовка картинки.

Винесено з ``vision.py`` (BE-S12): це крок *перед* дзвінком до моделі — визначити, що
відправляти (``select_targets``), і вирізати відповідну ділянку сторінки (``crop_png``).
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from .datatypes import BBox, Node, SourceRef
from .vision_client import VisionError

LOW_CONF = 60.0
CROP_PAD = 14
TOKENS_PER_TILE = 258         # Gemini: картинка ≤ 384 px — 258 токенів, більші ріжуться на плитки 768×768


@dataclass
class VisionTarget:
    exercise: Node
    reasons: list[str]

    @property
    def source(self) -> SourceRef | None:
        return self.exercise.source


def _written_subitems(ex: Node) -> list[Node]:
    return [c for c in ex.children if c.kind == "subexercise"]


def exercise_ocr_text(ex: Node) -> str:
    """Те, що OCR прочитав для вправи: умова + підпункти «N) текст»."""
    condition = ex.data.get("condition") or (ex.text.splitlines()[0] if ex.text else "")
    parts = [condition]
    parts += [f"{s.number}) {s.text}" for s in _written_subitems(ex)]
    if ex.data.get("condition_tail"):
        parts.append(ex.data["condition_tail"])
    return "\n".join(p for p in parts if p)


def select_targets(root: Node, layouts: Iterable[Any] = (), conf_threshold: float = LOW_CONF) -> list[VisionTarget]:
    """Вправи, які варто показати моделі, з причинами:
    needs_review, дріб на картинці (has_fractions), зламаний вираз, рядок з низьким conf."""
    low_conf_keys = {(lay.pdf_page, ln.line_id) for lay in layouts for ln in lay.body_lines
                     if ln.words and ln.conf < conf_threshold}
    targets = []
    for ex in root.find("exercise"):
        reasons = []
        if ex.data.get("has_fractions"):
            reasons.append("fraction_zone")
        if any(s.data.get("expr_status") == "malformed" for s in ex.walk()):
            reasons.append("expr_malformed")
        if ex.needs_review or any(s.needs_review for s in ex.walk() if s is not ex):
            reasons.append("needs_review")
        if low_conf_keys and any(tuple(k) in low_conf_keys for k in ex.data.get("line_keys", [])):
            reasons.append("low_conf")
        if reasons and ex.source and ex.source.bbox:
            targets.append(VisionTarget(ex, reasons))
    # Спершу найцінніші: дроби і зламані вирази, потім решта (за сторінкою).
    priority = {"fraction_zone": 0, "expr_malformed": 1, "needs_review": 2, "low_conf": 3}
    targets.sort(key=lambda t: (min(priority[r] for r in t.reasons), t.source.pdf_page))
    return targets


def crop_png(image: np.ndarray, box: BBox, pad: int = CROP_PAD) -> bytes:
    h, w = image.shape[:2]
    crop = image[max(0, box.y0 - pad):min(h, box.y1 + pad), max(0, box.x0 - pad):min(w, box.x1 + pad)]
    if crop.size == 0:
        raise VisionError(f"Порожня вирізка для {box}")
    ok, buf = cv2.imencode(".png", crop)
    if not ok:
        raise VisionError("Не вдалося закодувати PNG")
    return buf.tobytes()


def estimate_tokens(width: int, height: int) -> int:
    if width <= 384 and height <= 384:
        return TOKENS_PER_TILE
    return TOKENS_PER_TILE * math.ceil(width / 768) * math.ceil(height / 768)
