"""Міграція старих даних (план 21В.2): блоки зі старого import_content_blocks і розділи без Textbook.

Старий блок — ContentBlock без source_page (новий імпортер завжди його ставить). Видаляємо такий блок
лише коли його урок (пункт чи параграф) уже має нові блоки й сам блок не правився вручну.
Усі функції ідемпотентні й нічого не чіпають, поки не викликано з apply=True.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class LegacyReport:
    legacy_blocks: int = 0
    deletable: int = 0
    kept_no_new: int = 0          # у уроці ще немає нових блоків — старі лишаємо
    kept_manual: int = 0          # правилися вручну
    sections_total: int = 0
    sections_without_textbook: int = 0
    sections_backfillable: int = 0
    sections_orphan: list = field(default_factory=list)   # (клас, № розділу): для класу немає Textbook
    items_total: int = 0
    items_without_textbook: int = 0
    by_textbook: dict = field(default_factory=dict)       # profile_code -> {sections, items, blocks, exercises}


def _legacy_split(ContentBlock):
    legacy = ContentBlock.objects.filter(source_page__isnull=True)
    new = ContentBlock.objects.filter(source_page__isnull=False)
    new_items = set(new.exclude(item=None).values_list("item_id", flat=True))
    new_pars = set(new.exclude(paragraph=None).values_list("paragraph_id", flat=True))
    deletable, no_new, manual = [], 0, 0
    for b in legacy.only("pk", "item_id", "paragraph_id", "text_source"):
        if b.text_source == "manual":
            manual += 1
        elif (b.item_id in new_items) or (b.paragraph_id in new_pars):
            deletable.append(b.pk)
        else:
            no_new += 1
    return legacy.count(), deletable, no_new, manual


def sections_to_backfill(Section, Textbook):
    """[(section, textbook)] — розділи без підручника, для класу яких є рівно один Textbook."""
    by_grade = {}
    for tb in Textbook.objects.all():
        by_grade.setdefault(tb.grade_id, []).append(tb)
    out, orphan = [], []
    for s in Section.objects.filter(textbook__isnull=True).select_related("grade"):
        tbs = by_grade.get(s.grade_id, [])
        (out if len(tbs) == 1 else orphan).append((s, tbs[0]) if len(tbs) == 1 else (s.grade.number, s.number))
    return out, orphan


def backfill_section_textbooks(Section, Textbook) -> int:
    pairs, _ = sections_to_backfill(Section, Textbook)
    for section, tb in pairs:
        section.textbook = tb
        section.save(update_fields=["textbook"])
    return len(pairs)


def audit(apply: bool = False, models=None) -> LegacyReport:
    from . import models as m
    ContentBlock, Section, Item, Textbook, Exercise = (m.ContentBlock, m.Section, m.Item, m.Textbook, m.Exercise)
    rep = LegacyReport()
    rep.legacy_blocks, deletable, rep.kept_no_new, rep.kept_manual = _legacy_split(ContentBlock)
    rep.deletable = len(deletable)
    pairs, orphan = sections_to_backfill(Section, Textbook)
    rep.sections_backfillable, rep.sections_orphan = len(pairs), sorted(orphan)
    if apply:
        ContentBlock.objects.filter(pk__in=deletable).delete()
        backfill_section_textbooks(Section, Textbook)
    rep.sections_total = Section.objects.count()
    rep.sections_without_textbook = Section.objects.filter(textbook__isnull=True).count()
    rep.items_total = Item.objects.count()
    rep.items_without_textbook = Item.objects.filter(paragraph__section__textbook__isnull=True).count()
    for tb in Textbook.objects.all():
        rep.by_textbook[tb.profile_code] = {
            "sections": Section.objects.filter(textbook=tb).count(),
            "items": Item.objects.filter(paragraph__section__textbook=tb).count(),
            "blocks": ContentBlock.objects.filter(source_page__isnull=False).filter(
                _in_textbook(tb)).count(),
            "exercises": Exercise.objects.filter(textbook=tb).count(),
        }
    return rep


def _in_textbook(tb):
    from django.db.models import Q
    return Q(item__paragraph__section__textbook=tb) | Q(paragraph__section__textbook=tb)


def _lesson_key(grade, section, paragraph, item, block_type):
    return (grade, section, paragraph, item, block_type)


def old_block_counts(db_path: str, only_legacy: bool = True) -> Counter:
    """Кількість блоків за (клас, розділ, §, пункт|None, тип) у старій копії БД (sqlite)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("pragma table_info(education_contentblock)")}
        where = "where b.source_page is null" if only_legacy and "source_page" in cols else ""
        rows = con.execute(f"""
            select g.number, s.number, p.number, i.number, b.block_type
            from education_contentblock b
            left join education_item i on i.id = b.item_id
            join education_paragraph p on p.id = coalesce(i.paragraph_id, b.paragraph_id)
            join education_section s on s.id = p.section_id
            join education_grade g on g.id = s.grade_id {where}""").fetchall()
    finally:
        con.close()
    return Counter(_lesson_key(*r) for r in rows)


def new_block_counts() -> Counter:
    from .models import ContentBlock
    cnt = Counter()
    qs = ContentBlock.objects.filter(source_page__isnull=False).select_related(
        "item__paragraph__section__grade", "paragraph__section__grade")
    for b in qs:
        par = b.item.paragraph if b.item_id else b.paragraph
        sec = par.section
        cnt[_lesson_key(sec.grade.number, sec.number, par.number, b.item.number if b.item_id else None, b.block_type)] += 1
    return cnt


def compare(old: Counter, new: Counter):
    """[(ключ, було, стало)] лише для ключів, де кількість різна, за порядком ключів."""
    keys = sorted(set(old) | set(new), key=lambda k: (k[0], k[1], k[2], -1 if k[3] is None else k[3], k[4]))
    return [(k, old[k], new[k]) for k in keys if old[k] != new[k]]


def comparison_markdown(rows, old_total: int, new_total: int, label: str) -> str:
    out = [f"### Порівняння старих і нових блоків ({label})", "",
           f"Старих блоків: {old_total}, нових: {new_total}, відмінних ключів: {len(rows)}.", "",
           "| Клас | Розділ | § | Пункт | Тип блоку | Було | Стало |", "|---|---|---|---|---|---|---|"]
    for (g, s, p, i, t), a, b in rows:
        out.append(f"| {g} | {s} | {p} | {i if i is not None else '—'} | {t} | {a} | {b} |")
    return "\n".join(out) + "\n"
