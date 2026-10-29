"""Етап 6: структурний парсер — рядки всіх сторінок → дерево підручника.

BE-S11 розбив 697-рядковий файл на три шари; BE-S + «не виглядає добре»
(docs/backend/PLAN.md) згорнув їх у підпакет `structure/`, а цей `__init__.py`
лишається тонким реекспортом, щоб усі існуючі ``from .structure import ...`` і
``from education.pdf_pipeline.structure import ...`` продовжували працювати
без жодної зміни викликів:

- ``ocr_fix.py``   — відновлення номерів вправ, зіпсованих OCR;
- ``lines.py``     — потік рядків сторінки і звірка заголовків зі змістом;
- ``parser.py``    — сам автомат (``StructureParser``) і його результат.
"""
from __future__ import annotations

from .lines import (
    PARAGRAPH_LOOKAHEAD,
    TITLE_MATCH,
    PageLine,
    ParseIssue,
    iter_body_lines,
)
from .ocr_fix import letter_number_candidates, number_fixable
from .parser import (
    CONFIRM_MIN_CONF,
    CONFIRMABLE_FIXES,
    EXERCISE_BLOCKS,
    MAX_EXERCISE_JUMP,
    MAX_EXERCISE_RESYNC,
    NOISE_HEIGHT_HIGH,
    NOISE_HEIGHT_LOW,
    PARAGRAPH_LEVEL_BLOCKS,
    RESYNC_LOOKAHEAD,
    ParseResult,
    StructureParser,
    outline,
    parse_structure,
)

__all__ = [
    "PARAGRAPH_LOOKAHEAD",
    "TITLE_MATCH",
    "PageLine",
    "ParseIssue",
    "iter_body_lines",
    "letter_number_candidates",
    "number_fixable",
    "CONFIRM_MIN_CONF",
    "CONFIRMABLE_FIXES",
    "EXERCISE_BLOCKS",
    "MAX_EXERCISE_JUMP",
    "MAX_EXERCISE_RESYNC",
    "NOISE_HEIGHT_HIGH",
    "NOISE_HEIGHT_LOW",
    "PARAGRAPH_LEVEL_BLOCKS",
    "RESYNC_LOOKAHEAD",
    "ParseResult",
    "StructureParser",
    "outline",
    "parse_structure",
]
