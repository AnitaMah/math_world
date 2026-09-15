"""
Generic, subject-agnostic parser for curriculum table-of-contents text.

Problem this solves
--------------------
The project's only importer (import_programm_csv) required someone to
hand-retype the textbook's table of contents into a CSV, one row per
lesson. That's slow, error-prone, and it silently swallowed structure:
historical "aside" boxes (bulleted sub-entries such as "• Від ліктів та
долонь до метричної системи") got lost, and there was no way to tell a
real lesson heading apart from administrative noise like "Завдання № 3
«Перевірте себе» в тестовій формі" (a self-test blurb), "Головне в
параграфі 2" (a chapter summary), or "Зміст 271" (running-header page-
number bleed from copy/pasting the contents page).

This module reads the raw table-of-contents text line by line and
classifies each line using a SubjectProfile (see subject_profiles.py),
then assembles the result into Section -> Paragraph -> Item records
ready to hand to the import_curriculum management command. It makes no
assumption that every subject looks like a math textbook: a subject
profile with different markers (or none at all) still produces a
sensible hierarchy, falling back to a single auto-created section/
paragraph when no "Розділ"/"§" markers are present.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from .subject_profiles import SubjectProfile, MATH_PROFILE


@dataclass
class ItemRecord:
    number: int
    content: str


@dataclass
class ParagraphRecord:
    number: int
    title: str
    items: List[ItemRecord] = field(default_factory=list)


@dataclass
class SectionRecord:
    number: int
    title: str
    paragraphs: List[ParagraphRecord] = field(default_factory=list)


def parse_toc(
    lines: List[str], profile: SubjectProfile = MATH_PROFILE
) -> Tuple[List[SectionRecord], List[str]]:
    """
    Parse raw table-of-contents lines into a Section > Paragraph > Item
    tree, using `profile` to recognize this subject's markers.

    Returns (sections, skipped_lines) so the caller (the management
    command) can report how many administrative/noise lines were
    dropped, for visibility rather than silent data loss.
    """
    sections: List[SectionRecord] = []
    current_section: SectionRecord | None = None
    current_paragraph: ParagraphRecord | None = None
    current_item: ItemRecord | None = None
    skipped: List[str] = []

    def ensure_section() -> SectionRecord:
        nonlocal current_section
        if current_section is None:
            current_section = SectionRecord(
                number=len(sections) + 1, title=profile.default_section_title
            )
            sections.append(current_section)
        return current_section

    def ensure_paragraph() -> ParagraphRecord:
        nonlocal current_paragraph
        sec = ensure_section()
        if current_paragraph is None:
            current_paragraph = ParagraphRecord(
                number=len(sec.paragraphs) + 1, title=profile.default_paragraph_title
            )
            sec.paragraphs.append(current_paragraph)
        return current_paragraph

    for raw in lines:
        line = raw.strip()

        if not line:
            if profile.blank_line_ends_item:
                current_item = None
            continue

        if any(rx.match(line) for rx in profile.skip_res):
            skipped.append(line)
            continue

        if profile.part_re.match(line):
            current_section = SectionRecord(number=len(sections) + 1, title=line)
            sections.append(current_section)
            current_paragraph = None
            current_item = None
            continue

        m = profile.section_re.match(line)
        if m:
            sec = ensure_section()
            current_paragraph = ParagraphRecord(number=int(m.group(1)), title=line)
            sec.paragraphs.append(current_paragraph)
            current_item = None
            continue

        item_match = None
        for item_re in profile.item_res:
            item_match = item_re.match(line)
            if item_match:
                break
        if item_match:
            para = ensure_paragraph()
            current_item = ItemRecord(
                number=int(item_match.group(1)), content=item_match.group(2).strip()
            )
            para.items.append(current_item)
            continue

        m = profile.bullet_re.match(line)
        if m:
            if current_item is not None:
                current_item.content += "\n• " + m.group(1).strip()
            else:
                para = ensure_paragraph()
                current_item = ItemRecord(
                    number=len(para.items) + 1, content=m.group(1).strip()
                )
                para.items.append(current_item)
            continue

        # Unmarked continuation text: keep extending the current item if
        # one is open, otherwise start a new one. This is what lets a
        # subject with no numbering at all (plain paragraphs of prose)
        # still import as one item per paragraph.
        if current_item is not None:
            current_item.content += "\n" + line
        else:
            para = ensure_paragraph()
            current_item = ItemRecord(number=len(para.items) + 1, content=line)
            para.items.append(current_item)

    return sections, skipped
