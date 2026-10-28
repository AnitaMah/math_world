"""Дані мапи-архіпелагу (контракт `docs/frontend/DECISIONS.md`, моки `static/education/mock/`).

Одне місце, що рахує для класу: уроки (пункти Мерзляка або параграфи Тарасенкової), їхні завдання,
зірки гравця, **стан** кожного уроку (`done/current/open/locked/soon`) і поточний урок.
Views (`api.py`) лише віддають результат. Відповідей тут немає.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import Count, Prefetch

from .game import lesson_tasks
from .models import ContentBlock, Grade, Item, LessonProgress, Paragraph, Player, SchoolClass, Section, Textbook
from .services import playable_counts

# Блоки, які знає контракт (теги в панелі уроку), у порядку показу
CONTRACT_BLOCKS = ("theory", "self_check", "oral_exercise", "exercise", "review_exercise", "wise_owl",
                   "history_aside")
BLOCK_ALIASES = {"self_test": "self_check"}      # «Перевірте себе» Тарасенкової = самоперевірка
ISLAND_COUNT = 5                                  # кольорів островів у дизайні (isl-1 … isl-5)
MAX_STARS = 3


@dataclass
class Lesson:
    kind: str                       # item | paragraph
    obj: Item | Paragraph
    paragraph: Paragraph
    section: Section
    title: str
    auto: int = 0
    ai: int = 0
    solved: int = 0
    stars: int = 0
    blocks: list[str] = field(default_factory=list)
    state: str = "soon"

    @property
    def total(self) -> int:
        return self.auto + self.ai

    def as_dict(self) -> dict:
        return {"id": self.obj.pk, "number": self.obj.number, "title": self.title, "state": self.state,
                "stars": self.stars, "solved": self.solved, "total": self.total,
                "tasks": {"auto": self.auto, "ai": self.ai}, "blocks": self.blocks,
                "map": {"x": self.obj.map_x, "y": self.obj.map_y}}


def assign_states(rows: list[tuple[int, int]]) -> tuple[list[str], int | None]:
    """Правило «по черзі» з DECISIONS: рядки `(кількість завдань, зірки)` у порядку книги → стани й індекс поточного.

    - без завдань → `soon` (стежку не блокує);
    - є зірка → `done` (і наступний урок відкривається; відкрите раніше не закривається);
    - перший урок без зірок у відкритому ланцюгу → `current`; інші відкриті → `open`; решта → `locked`.
    """
    states: list[str] = []
    unlocked = True
    current: int | None = None
    for i, (total, stars) in enumerate(rows):
        if total == 0:
            states.append("soon")
        elif stars > 0:
            states.append("done")
            unlocked = True
        elif unlocked:
            if current is None:
                current = i
                states.append("current")
            else:
                states.append("open")
            unlocked = False
        else:
            states.append("locked")
    return states, current


def _block_types(lessons: list[Lesson]) -> dict[tuple[str, int], set[str]]:
    found: dict[tuple[str, int], set[str]] = {}
    items = [l.obj for l in lessons if l.kind == "item"]
    paragraphs = [l.obj for l in lessons if l.kind == "paragraph"]
    for field_name, kind, objs in (("item_id", "item", items), ("paragraph_id", "paragraph", paragraphs)):
        if not objs:
            continue
        rows = (ContentBlock.objects.filter(**{f"{field_name}__in": [o.pk for o in objs]})
                .values_list(field_name, "block_type").distinct())
        for pk, block_type in rows:
            found.setdefault((kind, pk), set()).add(BLOCK_ALIASES.get(block_type, block_type))
    return found


@dataclass
class GradeMap:
    grade: Grade
    textbook: Textbook | None
    sections: list[Section]
    lessons: list[Lesson]
    current: Lesson | None
    paragraph_island: dict[int, int]
    stars: int

    @property
    def paragraphs(self) -> list[Paragraph]:
        return [p for s in self.sections for p in s.paragraphs_ordered]


def load_grade(grade: Grade, player: Player | None = None, lang: str = "uk") -> GradeMap:
    """Усі уроки класу зі станами. Запитів — кілька на клас (не на урок): ігрові завдання рахуємо лише там, де є вправи.

    lang (фаза 20, беклог FE-0642) — мова назв уроків/параграфів; де `*_de` ще порожнє,
    `_item_title`/`get_name` самі падають назад на українську."""
    sections = list(Section.objects.filter(grade=grade).order_by("number"))
    paragraphs = list(Paragraph.objects.filter(section__in=sections).order_by("section__number", "number")
                      .select_related("section")
                      .prefetch_related(Prefetch("item_set", queryset=Item.objects.order_by("number"))))
    by_section: dict[int, list[Paragraph]] = {}
    for p in paragraphs:
        by_section.setdefault(p.section_id, []).append(p)
    for s in sections:
        s.paragraphs_ordered = by_section.get(s.pk, [])

    from .views import _item_title

    lessons: list[Lesson] = []
    island: dict[int, int] = {}
    for idx, p in enumerate(paragraphs):
        island[p.pk] = idx % ISLAND_COUNT + 1
        items = list(p.item_set.all())
        if items:
            for it in items:
                lessons.append(Lesson("item", it, p, p.section, _item_title(it, lang)))
        else:                                    # Тарасенкова: урок = параграф
            lessons.append(Lesson("paragraph", p, p, p.section, p.get_name(lang)))

    # завдання лише для уроків, де є ігрові вправи
    for kind, model in (("item", Item), ("paragraph", Paragraph)):
        group = [l for l in lessons if l.kind == kind]
        if not group:
            continue
        counts = playable_counts([l.obj for l in group])
        for l in group:
            if counts.get(l.obj.pk):
                tasks = lesson_tasks(l.obj, player)
                l.auto = sum(t.kind == "auto" for t in tasks)
                l.ai = sum(t.kind == "ai" for t in tasks)
                l.solved = sum(t.solved for t in tasks)

    stars: dict[tuple[str, int], int] = {}
    if player is not None:
        for pr in LessonProgress.objects.filter(player=player):
            stars[("item", pr.item_id) if pr.item_id else ("paragraph", pr.paragraph_id)] = pr.stars
    blocks = _block_types(lessons)
    for l in lessons:
        l.stars = stars.get((l.kind, l.obj.pk), 0) if l.total else 0
        l.blocks = [b for b in CONTRACT_BLOCKS if b in blocks.get((l.kind, l.obj.pk), ())]

    states, cur = assign_states([(l.total, l.stars) for l in lessons])
    for l, st in zip(lessons, states):
        l.state = st
    return GradeMap(grade, Textbook.objects.filter(grade=grade).order_by("pk").first(), sections, lessons,
                    lessons[cur] if cur is not None else None, island, sum(l.stars for l in lessons))


def map_payload(gm: GradeMap, lang: str = "uk") -> dict:
    """Тіло `GET /api/grades/<n>/map/`. lang — фаза 20, беклог FE-0642 (назви розділів і §:
    уроки-пункти вже отримали свою назву мовою lang у load_grade())."""
    by_par: dict[int, list[Lesson]] = {}
    for l in gm.lessons:
        by_par.setdefault(l.paragraph.pk, []).append(l)
    sections = []
    for s in gm.sections:
        paragraphs = []
        for p in s.paragraphs_ordered:
            own = by_par.get(p.pk, [])
            entry = {"id": p.pk, "number": p.number, "title": p.get_name(lang)}
            if own and own[0].kind == "paragraph":
                entry.update(own[0].as_dict() | {"id": p.pk, "number": p.number, "title": p.get_name(lang)})
                entry["items"] = []
            else:
                entry["items"] = [l.as_dict() for l in own]
            paragraphs.append(entry)
        sections.append({"id": s.pk, "number": s.number, "title": s.get_name(lang), "paragraphs": paragraphs})
    tb = gm.textbook
    return {"grade": gm.grade.number, "subject": gm.grade.subject.code,
            "textbook": {"author": tb.author, "year": tb.year} if tb else None,
            "current": {"kind": gm.current.kind, "id": gm.current.obj.pk} if gm.current else None,
            "sections": sections}


def grade_summary(gm: GradeMap) -> dict:
    """Елемент `GET /api/grades/` (екран «Світ»)."""
    tb = gm.textbook
    cur = gm.current
    return {"number": gm.grade.number, "subject": gm.grade.subject.code,
            "author": tb.author if tb else "", "year": tb.year if tb else None,
            "sections": len(gm.sections), "lessons": len(gm.lessons),
            "playable_lessons": sum(l.total > 0 for l in gm.lessons),
            "stars": gm.stars, "max_stars": MAX_STARS * len(gm.lessons),
            "current": {"kind": cur.kind, "id": cur.obj.pk, "number": cur.obj.number} if cur else None}


def find_lesson(kind: str, lesson: Item | Paragraph, player: Player | None) -> tuple[GradeMap, Lesson]:
    """Урок разом із картою його класу (для стану `locked` і кольору острова в грі)."""
    paragraph = lesson.paragraph if kind == "item" else lesson
    gm = load_grade(paragraph.section.grade, player)
    found = next(l for l in gm.lessons if l.kind == kind and l.obj.pk == lesson.pk)
    return gm, found


def class_star_payload(school_class: SchoolClass, grade: Grade, lang: str = "uk") -> dict:
    """Тіло `GET /api/classes/<id>/grades/<n>/stars/` — контракт для FE-0645 (режим вчителя).

    Для кожного уроку/вузла шкільного класу (групи учнів вчителя, не плутати зі «шкільним класом»
    у значенні grade тут) — скільком учням зараховано зірку (``LessonProgress.stars > 0``) і яка
    це частка від усіх учнів групи.
    """
    gm = load_grade(grade, lang=lang)
    student_ids = list(school_class.students.values_list("user_id", flat=True))
    total = len(student_ids)
    rows = (LessonProgress.objects.filter(player__user_id__in=student_ids, stars__gt=0)
            .values("item_id", "paragraph_id").annotate(n=Count("pk")))
    with_star: dict[tuple[str, int], int] = {}
    for r in rows:
        key = ("item", r["item_id"]) if r["item_id"] else ("paragraph", r["paragraph_id"])
        with_star[key] = r["n"]
    lessons = []
    for l in gm.lessons:
        n = with_star.get((l.kind, l.obj.pk), 0)
        lessons.append({"kind": l.kind, "id": l.obj.pk, "with_star": n,
                        "percent": round(n * 100 / total) if total else 0})
    return {"class_id": school_class.pk, "grade": grade.number, "total_students": total, "lessons": lessons}
