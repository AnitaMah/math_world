"""Рамки на сторінці: таблиці-рисунки і текстові рамки («Зверніть увагу:»).

Шукаємо довгі горизонтальні й вертикальні лінії (морфологічне «відкриття»
довгим тонким ядром прибирає літери й лишає лише лінії) і обводимо їх
зовнішніми контурами. Що це за рамка — текстова чи рисунок — вирішує
layout за тим, скільки тексту всередині.
"""
from __future__ import annotations

import cv2
import numpy as np

from ..datatypes import BBox

MIN_FRAME_AREA = 0.005    # рамки, менші за 0.5% площі сторінки, ігноруємо


def detect_frames(image: np.ndarray, min_area: float = MIN_FRAME_AREA) -> list[BBox]:
    """Прямокутники, утворені лініями (рамки, таблиці), у координатах цієї картинки."""
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Ядро 1×(w/15): лишаються лише горизонтальні відрізки довжиною ≥ w/15. Аналогічно вертикальні.
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(w // 15, 1), 1)))
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(h // 30, 1))))
    contours, _ = cv2.findContours(cv2.bitwise_or(horizontal, vertical), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    frames: list[BBox] = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if bw * bh >= min_area * w * h and bw > 10 and bh > 10:
            frames.append(BBox(x, y, x + bw, y + bh))
    return sorted(frames, key=lambda b: (b.y0, b.x0))
