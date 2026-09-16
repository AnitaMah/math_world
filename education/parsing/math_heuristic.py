"""
Step 28 of the refactor plan: a cheap, local (no API calls) heuristic
that flags whether a piece of OCR'd text likely contains math notation
that Tesseract probably mangled -- fractions, exponents, roots, geometric
figures, and the like are drawn as glyphs on the page, not real
selectable text, so plain OCR guesses at them character-by-character and
often gets it wrong.

This is the actual quota-control mechanism for Step 29 (Gemini vision
OCR): only text flagged here gets a (rate-limited, free-tier) image call
sent to Gemini. Everything else stays on the free, unlimited Tesseract
pass. Keep this conservative -- flagging too much defeats the point.

No AI involved here on purpose: this is meant to run over every block
for free, as many times as needed, before a single paid/rate-limited API
call gets made.
"""
from __future__ import annotations

import re

# Instructional phrases that reliably introduce a math exercise/formula
# in this textbook's Ukrainian, based on the sections already reviewed
# in this project (Кроки 14+ of the refactor plan).
MATH_MARKER_PHRASES = (
    "обчисліть",
    "розв'яжіть рівняння",
    "розв'язати рівняння",
    "знайдіть значення",
    "спростіть вираз",
    "порівняйте",
    "накресліть",
    "побудуйте",
    "периметр",
    "площа",
)

# Characters/patterns that are common in real math notation but rare in
# plain Ukrainian prose. A high density of these relative to plain words
# suggests the OCR is fighting with drawn symbols (fractions, exponents,
# etc.) rather than reading normal sentences.
MATH_SYMBOL_RE = re.compile(r"[=<>±√∙×÷%^]|\d+/\d+|\d+\^\d+")

# A lone digit or a very short "word" made only of digits/symbols,
# surrounded by whitespace -- typical of a mis-OCR'd fraction or exponent
# that got split across several garbled tokens.
ISOLATED_SYMBOL_TOKEN_RE = re.compile(r"(?<!\S)[\d=<>±√∙×÷%^./\\-]{1,3}(?!\S)")


def needs_vision_ocr(text: str, threshold: float = 0.08) -> bool:
    """
    Returns True if `text` (raw OCR output for one block/region) looks
    math-heavy enough to be worth a Gemini vision OCR re-pass instead of
    trusting Tesseract's output as-is.

    `threshold` is the fraction of "suspicious" tokens (isolated
    digit/symbol fragments) among all whitespace-separated tokens, above
    which we flag the block. Tuned conservatively -- err on the side of
    NOT flagging, since every flagged block costs a rate-limited API call
    later (Step 29).
    """
    if not text or not text.strip():
        return False

    lowered = text.lower()

    # Strong signal: explicit exercise/formula markers common in this
    # textbook almost always accompany real math notation nearby.
    if any(phrase in lowered for phrase in MATH_MARKER_PHRASES):
        return True

    # Explicit math symbols (=, fractions written as a/b, exponents as
    # a^b, etc.) are a direct, unambiguous signal.
    if MATH_SYMBOL_RE.search(text):
        return True

    # Otherwise, fall back to token-density: lots of short garbled
    # digit/symbol fragments relative to total tokens usually means
    # Tesseract chopped up a fraction/exponent/diagram label into noise.
    tokens = text.split()
    if not tokens:
        return False

    suspicious = sum(1 for t in tokens if ISOLATED_SYMBOL_TOKEN_RE.fullmatch(t))
    return (suspicious / len(tokens)) >= threshold


def annotate_blocks(blocks: list[dict]) -> list[dict]:
    """
    Convenience wrapper for the import pipeline: given a list of block
    dicts each with a "text" key, returns the same list with a
    "needs_vision_ocr" bool added to each. Used by Step 30's --vision-ocr
    flag to decide which blocks get a Gemini image call.
    """
    for block in blocks:
        block["needs_vision_ocr"] = needs_vision_ocr(block.get("text", ""))
    return blocks
