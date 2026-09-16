"""
Tracks, per grade, what source material exists and which
SubjectProfile (education/parsing/subject_profiles.py) applies to it.

This is a plain data manifest, not code that runs anything -- it exists
so "which grades are actually ready to import" is one file to check
instead of scattered conversation history. Update it as each grade's
source material is obtained/processed.

status meanings:
    "imported"     -- clean .txt exists and has been run through
                       import_curriculum successfully (verified in DB).
    "pdf_only"      -- a textbook PDF exists in the project but hasn't
                       been rendered/OCR'd/reviewed yet (Steps 12-14).
    "profile_unconfirmed" -- OCR'd text exists (or is expected to) but
                       the SubjectProfile hasn't been validated against
                       this book's real heading format yet.
    "missing"      -- no source material at all yet.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class GradeSource:
    grade: int
    subject_code: str
    profile: str          # key into education.parsing.subject_profiles.PROFILES
    textbook: str          # author/title, for humans
    pdf_path: Optional[str]
    clean_txt_path: Optional[str]
    status: str


GRADE_SOURCES = [
    GradeSource(
        grade=5,
        subject_code="math",
        profile="math_merzlyak",
        textbook="Мерзляк, 2018",
        pdf_path="5-klas-matematika-merzljak-2018-1-46.pdf",  # pages 1-46 only
        clean_txt_path="data/5_class_ukr.txt",
        status="imported",
    ),
    GradeSource(
        grade=6,
        subject_code="math",
        profile="math_tarasenkova",
        textbook="Тарасенкова, повний підручник",
        pdf_path="Matematyka_6klas_Tarasenkova.pdf",
        clean_txt_path="data/6_class_ukr.txt",
        # Розділ/§ only -- reconstructed from the real contents page
        # (PDF pages 303-304), which is heavily OCR-garbled (dot leaders,
        # "§" misread as a stray digit) and doesn't list individual
        # lesson titles at all, unlike Merzlyak's TOC. Item rows will be
        # empty until lesson titles are extracted from each §'s actual
        # pages in a later step -- see refactor plan Step 36.
        status="sections_only_no_items",
    ),
    GradeSource(
        grade=7,
        subject_code="math",
        profile=None,
        textbook=None,
        pdf_path=None,
        clean_txt_path=None,
        status="missing",
    ),
    GradeSource(
        grade=8,
        subject_code="math",
        profile=None,
        textbook=None,
        pdf_path=None,
        clean_txt_path=None,
        status="missing",
    ),
    GradeSource(
        grade=9,
        subject_code="math",
        profile=None,
        textbook=None,
        pdf_path=None,
        clean_txt_path=None,
        status="missing",
    ),
]


def get_source(grade: int) -> Optional[GradeSource]:
    return next((g for g in GRADE_SOURCES if g.grade == grade), None)
