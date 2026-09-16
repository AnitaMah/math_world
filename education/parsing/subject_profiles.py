"""
Subject-specific parsing rules for curriculum table-of-contents files.

Different school subjects lay out their table of contents differently.
A math textbook uses "Розділ" (Part, roman numeral) > "§ N." (paragraph) >
"N. Title" (numbered lesson) > "• Title" (optional historical/aside box).
A language-arts subject might instead use "Тема N." or "Урок N." with no
Part/§ nesting at all, and no "§" symbol whatsoever.

Rather than hard-code math's structure into the parser, each subject gets a
SubjectProfile describing which regular expressions identify each kind of
line. The parser (toc_parser.py) is generic and subject-agnostic; it just
asks the active profile "what kind of line is this?".

Add a new profile here (and register it in PROFILES) for each new subject
instead of editing the parser itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Pattern


@dataclass
class SubjectProfile:
    name: str

    # "Розділ I. ..." -- a top-level Part. Sequentially numbered regardless
    # of the roman numeral's actual value (robust to numbering typos).
    part_re: Pattern = field(
        default_factory=lambda: re.compile(r"^Розділ\s+[IVXLCDM]+\.")
    )

    # "§ 4. Звичайні дроби" -- maps to our Paragraph model.
    section_re: Pattern = field(
        default_factory=lambda: re.compile(r"^§\s*(\d+)\.\s*(.*)$")
    )

    # "25. Уявлення про звичайні дроби" -- maps to our Item model.
    # A list because some subjects use several markers ("N.", "Урок N.",
    # "Тема N."); the first pattern that matches wins.
    item_res: List[Pattern] = field(
        default_factory=lambda: [re.compile(r"^(\d+)\.\s*(.+)$")]
    )

    # "• Від ліктів та долонь до метричної системи" -- a historical /
    # "did you know" aside nested under the item above it. Folded into
    # that item's content rather than becoming its own row.
    bullet_re: Pattern = field(
        default_factory=lambda: re.compile(r"^[•·▪]\s*(.+)$")
    )

    # Lines that are structurally *noise* in a copy-pasted/OCR'd table of
    # contents and must never become content: self-test blurbs, chapter
    # summaries, back-matter, and running-header page-number bleed
    # ("Зміст 271" -- "Contents" + a stray page number).
    skip_res: List[Pattern] = field(
        default_factory=lambda: [
            re.compile(r"^Завдання\s*№\s*\d+", re.IGNORECASE),
            re.compile(r"^Головне\s+в\s+параграф", re.IGNORECASE),
            re.compile(r"^(Вправи для повторення|Відповіді)", re.IGNORECASE),
            re.compile(r"^Зміст\s*\d*$", re.IGNORECASE),
        ]
    )

    # If true, a blank line closes off the current item so that unmarked
    # continuation text after it starts a *new* item instead of being
    # silently appended to the previous one. Safe for math (no blank
    # lines inside an entry) and important for prose subjects where
    # paragraphs are separated by blank lines rather than markers.
    blank_line_ends_item: bool = True

    # Fallback titles used only when content appears before any explicit
    # Part/§ heading (e.g. a subject with no "Розділ"/"§" concept at all).
    default_section_title: str = "Загальний розділ"
    default_paragraph_title: str = "Загальний параграф"


# NOTE ON GRADES 5-9: a SubjectProfile is keyed to a *textbook/author*,
# not a grade number -- Grade is already free-standing (scoped by
# (number, subject) in the model, see import_curriculum.py), so nothing
# here needs to change to support grade 6, 7, 8, 9. What differs between
# grades is which author wrote that grade's book, and authors format
# their table of contents slightly differently. Add one profile per
# textbook you actually have source text for; reuse an existing profile
# across grades only once you've confirmed (by OCR'ing that grade's real
# TOC pages, Steps 12-14) that its heading conventions actually match.

# Confirmed against the real grade-5 Merzlyak textbook (see refactor plan
# Section 1). This is the one profile that's been validated end-to-end.
MATH_MERZLYAK_PROFILE = SubjectProfile(name="math_merzlyak")

# Grade 6 (Tarasenkova, Matematyka_6klas_Tarasenkova.pdf). Confirmed
# against the real contents page (pages 303-304 of the PDF -- this book's
# "Зміст" sits at the back, not the front): "Розділ" uses an ARABIC
# numeral ("РОЗДІЛ 5", confirmed unmangled in the answer key on page 297)
# unlike Merzlyak's Roman numerals. The contents page only lists
# Розділ/§ headings, not individual numbered lessons underneath each § --
# unlike Merzlyak's TOC, which listed lesson titles too. So for now this
# profile only produces Section/Paragraph rows; Item rows stay empty
# until lesson titles are extracted from each §'s actual pages in a
# later step. Also note: this book's OCR misreads "§" as a stray digit
# ("81." instead of "§1.") -- real "§" characters are used in the
# hand-corrected data/6_class_ukr.txt fixture, not the raw OCR output.
MATH_TARASENKOVA_PROFILE = SubjectProfile(
    name="math_tarasenkova",
    part_re=re.compile(r"^Розділ\s+(\d+)\.", re.IGNORECASE),
)

# "math" is kept as a backwards-compatible alias for Merzlyak (grade 5),
# since existing commands/tests already call --subject math.
MATH_PROFILE = MATH_MERZLYAK_PROFILE

# Ukrainian-language-arts style profile: numbered lessons may be labelled
# "Урок N." or "Тема N." in addition to a bare "N.", and there is
# typically no "§" concept. Adjust/extend once a real ukr-language TOC
# is available -- this is a starting point, not a final answer.
UKR_LANGUAGE_PROFILE = SubjectProfile(
    name="ukr_language",
    item_res=[
        re.compile(r"^Урок\s+(\d+)\.\s*(.+)$", re.IGNORECASE),
        re.compile(r"^Тема\s+(\d+)\.\s*(.+)$", re.IGNORECASE),
        re.compile(r"^(\d+)\.\s*(.+)$"),
    ],
)

GENERIC_PROFILE = SubjectProfile(name="generic")

PROFILES = {
    "math": MATH_PROFILE,
    "math_merzlyak": MATH_MERZLYAK_PROFILE,
    "math_tarasenkova": MATH_TARASENKOVA_PROFILE,
    "ukr_language": UKR_LANGUAGE_PROFILE,
    "generic": GENERIC_PROFILE,
}


def get_profile(name: str) -> SubjectProfile:
    return PROFILES.get(name, MATH_PROFILE)
