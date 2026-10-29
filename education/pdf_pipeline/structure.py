"""Етап 6: структурний парсер — рядки всіх сторінок → дерево підручника.

BE-S11: файл був 697 рядків і змішував три шари — тут лишається лише тонкий реекспорт,
щоб усі існуючі ``from .structure import ...`` і ``from education.pdf_pipeline.structure
import ...`` продовжували працювати без змін:

- ``structure_ocr_fix.py``   — відновлення номерів вправ, зіпсованих OCR;
- ``structure_lines.py``     — потік рядків сторінки і звірка заголовків зі змістом;
- ``structure_parser.py``    — сам автомат (``StructureParser``) і його результат.
"""
from __future__ import annotations

from .structure_lines import (
    PARAGRAPH_LOOKAHEAD,
    TITLE_MATCH,
    PageLine,
    ParseIssue,
    iter_body_lines,
)
from .structure_ocr_fix import letter_number_candidates, number_fixable
from .structure_parser import (
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
