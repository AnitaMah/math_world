"""Етап 6: структурний парсер — рядки всіх сторінок → дерево підручника.

    textbook
    └─ section (Розділ)              ← з профілю/змісту
       └─ paragraph (§)              ← заголовок на сторінці, звірений зі змістом
          └─ item (пункт, урок)      ← лише якщо profile.lesson_level == "item"
             └─ block (theory, oral_exercise, exercise, wise_owl, …)
                └─ exercise (номер, складність, текст)

Реалізація — скінченний автомат: ми йдемо по рядках згори вниз, і кожен рядок
або відкриває новий вузол (заголовок, рубрика, номер вправи), або дописується
в поточний. Невпевнені рішення не губимо — вони йдуть у ``issues`` з посиланням
на сторінку, щоб людина могла перевірити.
"""
from __future__ import annotations

import re
import statistics
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .datatypes import BBox, Line, Node, SourceRef
from .layout import PageLayout
from .profiles import TextbookProfile
from .profiles.base import TocEntry, normalize_marker_text, section_number

TITLE_MATCH = 85          # схожість заголовка на сторінці з назвою у змісті (0–100)
MAX_EXERCISE_JUMP = 5     # номер вправи може «перескочити» не більше ніж на стільки
NOISE_HEIGHT_HIGH = 2.2   # рядок у стільки разів вищий за медіану — це картинка, а не текст
NOISE_HEIGHT_LOW = 0.45
EXERCISE_BLOCKS = {"oral_exercise", "exercise", "review_exercise", "wise_owl", "applied_exercise"}
PARAGRAPH_LEVEL_BLOCKS = {"self_test", "summary"}   # належать §, а не пункту
# Номер у заголовку §, як його бачить OCR: «§ 1.», «9 1.», «51.», «S 1.»
_PARAGRAPH_PREFIX_RE = re.compile(r"^\W*(?:§|5|9|S|\$)?\s*(?P<num>\d{1,2})\s*\.\s*")
_ITEM_PREFIX_RE = re.compile(r"^\W*(?P<num>\d{1,2})\s*\.\s*")
# Початок вправи без крапки або зі зламаним значком: «82 Скільки», «4 Яке число», «4, Назвіть», «67" Точка»
_LOOSE_EXERCISE_RE = re.compile(r"^(?P<num>\d{1,4})(?P<junk>[,.\"”'°•·*]{0,3})\s+(?P<rest>[А-ЯІЇЄҐA-Z].*)$")
# Цифри, які OCR плутає між собою у цьому шрифті
_CONFUSABLE_DIGITS = {"3": "8", "8": "3", "5": "6", "6": "5", "1": "7", "7": "1", "0": "8"}


def number_fixable(raw: str, expected: int) -> bool:
    """Чи можна отримати ``expected`` з ``raw`` однією типовою помилкою OCR.

    «88» → 83 (3↔8), «168» → 163, «382» → 32 (зайва цифра — це був значок •),
    «82» → 8 (значок прочитано як цифру).
    """
    target = str(expected)
    if raw == target:
        return True
    for i in range(len(raw)):
        if raw[:i] + raw[i + 1:] == target:                                   # зайва цифра
            return True
        swapped = _CONFUSABLE_DIGITS.get(raw[i])
        if swapped and raw[:i] + swapped + raw[i + 1:] == target:            # сплутана цифра
            return True
    return False
_CAPTION_RE = re.compile(r"^(?:Рис|Мал|Puc)\.?\s*\d+", re.IGNORECASE)


# --------------------------------------------------------------------------- допоміжне


@dataclass(frozen=True)
class ParseIssue:
    """Місце, яке парсер не зміг впевнено розібрати."""

    code: str
    message: str
    pdf_page: int
    text: str = ""

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "pdf_page": self.pdf_page, "text": self.text}


@dataclass
class PageLine:
    """Рядок разом із його сторінкою (потік рядків усієї книги)."""

    line: Line
    layout: PageLayout

    @property
    def text(self) -> str:
        return self.line.text.strip()

    @property
    def key(self) -> tuple[int, int]:
        return (self.layout.pdf_page, self.line.line_id)

    def source(self) -> SourceRef:
        return SourceRef(pdf_page=self.layout.pdf_page, book_page=self.layout.book_page,
                         bbox=self.line.bbox, line_ids=(self.line.line_id,))


def iter_body_lines(layouts: Iterable[PageLayout], skip_pages: Iterable[int] = ()) -> Iterator[PageLine]:
    """Рядки тіла всіх сторінок по порядку (колонтитули вже прибрані в layout)."""
    skip = set(skip_pages)
    for layout in sorted(layouts, key=lambda lay: lay.pdf_page):
        if layout.pdf_page in skip:
            continue
        for line in layout.body_lines:
            if line.words:
                yield PageLine(line, layout)


def _title_score(text: str, title: str) -> float:
    return fuzz.ratio(normalize_marker_text(text), normalize_marker_text(title))


def _extend_bbox(source: SourceRef | None, line: PageLine) -> SourceRef:
    """Розширює SourceRef вузла ще одним рядком тієї ж сторінки (інші сторінки — лише line_ids)."""
    if source is None:
        return line.source()
    if source.pdf_page != line.layout.pdf_page or source.bbox is None:
        return source
    return SourceRef(source.pdf_page, source.book_page, source.bbox.union(line.line.bbox),
                     source.line_ids + (line.line.line_id,))


# --------------------------------------------------------------------------- парсер


@dataclass
class ParseResult:
    root: Node
    issues: list[ParseIssue] = field(default_factory=list)
    skipped_noise: int = 0

    def lessons(self) -> list[Node]:
        kind = "item" if self.root.find("item") else "paragraph"
        return self.root.find(kind)


class StructureParser:
    """Скінченний автомат над потоком рядків. Використання: ``StructureParser(profile).parse(layouts)``."""

    def __init__(self, profile: TextbookProfile, toc: Sequence[TocEntry] | None = None):
        self.profile = profile
        self.toc = list(toc) if toc is not None else profile.toc()
        self.root = Node("textbook", title=profile.title,
                         data={"profile": profile.code, "grade": profile.grade, "subject": profile.subject_code})
        self.issues: list[ParseIssue] = []
        self.skipped_noise = 0

        # Поточні відкриті вузли (стан автомата)
        self.section: Node | None = None
        self.paragraph: Node | None = None
        self.item: Node | None = None
        self.block: Node | None = None
        self.exercise: Node | None = None

        self.expected_exercise = 1          # наскрізна нумерація вправ
        self.block_counter = 0              # нумерація всередині блоку (усні вправи з 1)
        self._page_medians: dict[int, float] = {}

        self._section_of_paragraph = self._toc_section_map()

    # ------------------------------------------------------------------ зміст

    def _toc_section_map(self) -> dict[str, TocEntry]:
        """№ параграфа → розділ, якому він належить (за порядком у змісті)."""
        current: TocEntry | None = None
        mapping: dict[str, TocEntry] = {}
        for entry in self.toc:
            if entry.kind == "section":
                current = entry
            elif entry.kind == "paragraph" and current is not None:
                mapping[entry.number] = current
        return mapping

    def _toc_entries(self, kind: str) -> list[TocEntry]:
        return [e for e in self.toc if e.kind == kind]

    # ------------------------------------------------------------------ класифікація рядка

    def _is_noise(self, pl: PageLine) -> bool:
        """Сміття від картинок: рядок надто високий/низький або майже без літер і цифр."""
        page = pl.layout.pdf_page
        if page not in self._page_medians:
            heights = [ln.height for ln in pl.layout.body_lines if ln.words]
            self._page_medians[page] = statistics.median(heights) if heights else 0.0
        median = self._page_medians[page]
        h = pl.line.height
        if median and (h > NOISE_HEIGHT_HIGH * median or h < NOISE_HEIGHT_LOW * median):
            return True
        meaningful = sum(ch.isalnum() for ch in pl.text)
        return meaningful < 2

    def _match_paragraph(self, text: str) -> TocEntry | None:
        """Заголовок §? Номер + назва, що збігається з одним із § у змісті."""
        m = _PARAGRAPH_PREFIX_RE.match(text)
        if not m or not ("§" in text[:3] or text[:1] in "59S$"):
            return None
        rest = text[m.end():]
        for entry in self._toc_entries("paragraph"):
            if entry.number == m.group("num") and _title_score(rest, entry.title) >= TITLE_MATCH:
                return entry
        return None

    def _match_item(self, text: str) -> TocEntry | None:
        """Заголовок пункту? «2. Цифри. Десятковий запис…» — номер і назва зі змісту."""
        if self.profile.item_re is None:
            return None
        m = _ITEM_PREFIX_RE.match(text)
        if not m:
            return None
        rest = text[m.end():]
        for entry in self._toc_entries("item"):
            if entry.number == m.group("num") and _title_score(rest, entry.title) >= TITLE_MATCH:
                return entry
        return None

    def _match_marker(self, text: str) -> str | None:
        found = self.profile.match_block_marker(text)
        if not found:
            return None
        marker, _score = found
        if marker.whole_line:
            longest = max(len(p) for p in marker.phrases)
            if len(text) > longest * 1.5 + 6:      # довгий рядок — це речення, а не заголовок рубрики
                return None
        return marker.block_type

    def _match_exercise(self, text: str) -> tuple[int, str | None, str, bool] | None:
        """(номер, рівень, текст, номер_виправлено) або None.

        Порядок: точний збіг з очікуваним номером → типова помилка OCR (3↔8,
        зайва цифра) → невеликий стрибок уперед (пропущена вправа) → інакше це не вправа.
        """
        expected = self._expected_number()
        parsed = self.profile.parse_exercise_start(text)
        loose = None if parsed else _LOOSE_EXERCISE_RE.match(text)
        if parsed:
            num, level, rest = parsed
            raw = str(num)
        elif loose:
            raw, rest = loose.group("num"), loose.group("rest")
            junk = loose.group("junk").strip(",.")
            level = self.profile.difficulty_marks.get(junk, "unknown") if junk else self.profile.default_difficulty
            num = int(raw)
        else:
            return None

        if num == expected:
            return num, level, rest, False
        if number_fixable(raw, expected):
            return expected, level if parsed else "unknown", rest, True
        if parsed and self._number_plausible(num, expected):
            return num, level, rest, False
        return None

    def _expected_number(self) -> int:
        if self.block is not None and self.block.data.get("block_type") == "oral_exercise":
            return self.block_counter + 1
        return self.expected_exercise

    def _number_plausible(self, num: int, expected: int) -> bool:
        return expected <= num <= expected + MAX_EXERCISE_JUMP

    # ------------------------------------------------------------------ відкриття вузлів

    def _issue(self, code: str, message: str, pl: PageLine) -> None:
        self.issues.append(ParseIssue(code, message, pl.layout.pdf_page, pl.text[:120]))

    def _open_paragraph(self, entry: TocEntry, pl: PageLine) -> None:
        section_entry = self._section_of_paragraph.get(entry.number)
        if section_entry and (self.section is None or self.section.number != section_entry.number):
            self.section = self.root.add(Node("section", number=section_entry.number, title=section_entry.title,
                                              source=pl.source(),
                                              data={"index": section_number(section_entry.number)}))
        if self.section is None:
            self.section = self.root.add(Node("section", number="?", title="", source=pl.source()))
            self._issue("section_unknown", "Параграф без розділу у змісті", pl)
        self.paragraph = self.section.add(Node("paragraph", number=entry.number, title=entry.title,
                                               source=pl.source(), data={"ocr_title": pl.text}))
        self.item = None
        self.exercise = None
        self.block = None
        if self.profile.lesson_level == "paragraph":
            self._open_block("theory", pl)

    def _open_item(self, entry: TocEntry, pl: PageLine) -> None:
        if self.paragraph is None:
            self._issue("item_without_paragraph", "Пункт до першого §", pl)
            return
        self.item = self.paragraph.add(Node("item", number=entry.number, title=entry.title,
                                            source=pl.source(), data={"ocr_title": pl.text}))
        self.exercise = None
        self._open_block("theory", pl)

    def _lesson(self) -> Node | None:
        return self.item if self.profile.lesson_level == "item" else self.paragraph

    def _open_block(self, block_type: str, pl: PageLine, attach_to_paragraph: bool = False) -> None:
        parent = self.paragraph if attach_to_paragraph else (self._lesson() or self.paragraph)
        if parent is None:
            self._issue("block_without_lesson", f"Рубрика {block_type} до першого уроку", pl)
            return
        if attach_to_paragraph:
            self.item = None
        self.block = parent.add(Node("block", title=block_type if block_type == "theory" else pl.text,
                                     source=pl.source(), data={"block_type": block_type}))
        self.block_counter = 0
        self.exercise = None

    def _open_exercise(self, num: int, level: str | None, rest: str, fixed: bool, pl: PageLine) -> None:
        assert self.block is not None
        is_oral = self.block.data.get("block_type") == "oral_exercise"
        self.exercise = self.block.add(Node(
            "exercise", number=str(num), text=rest, source=pl.source(),
            needs_review=fixed or level == "unknown",
            data={"difficulty": level, "line_keys": [list(pl.key)], "number_fixed": fixed},
        ))
        if fixed:
            self._issue("exercise_number_fixed", f"Номер вправи відновлено як {num}", pl)
        if is_oral:
            self.block_counter = num
        else:
            if num != self.expected_exercise:
                self._issue("exercise_number_gap", f"Очікували {self.expected_exercise}, знайшли {num}", pl)
            self.expected_exercise = num + 1

    def _append_text(self, pl: PageLine) -> None:
        target = self.exercise or self.block
        if target is None:
            return      # текст до першого заголовка (титульні сторінки) — пропускаємо
        target.text = f"{target.text}\n{pl.text}" if target.text else pl.text
        target.source = _extend_bbox(target.source, pl)
        if self.exercise is not None:
            self.exercise.data["line_keys"].append(list(pl.key))
        else:
            target.data.setdefault("line_keys", []).append(list(pl.key))

    # ------------------------------------------------------------------ головний цикл

    def feed(self, pl: PageLine) -> None:
        """Обробити один рядок (таблиця переходів автомата)."""
        text = pl.text
        if self._is_noise(pl) or _CAPTION_RE.match(text):
            self.skipped_noise += 1
            return

        entry = self._match_paragraph(text)
        if entry:
            self._open_paragraph(entry, pl)
            return
        entry = self._match_item(text)
        if entry:
            self._open_item(entry, pl)
            return

        block_type = self._match_marker(text)
        if block_type:
            self._open_block(block_type, pl, attach_to_paragraph=block_type in PARAGRAPH_LEVEL_BLOCKS)
            return

        current = self.block.data.get("block_type") if self.block else None
        if current in EXERCISE_BLOCKS:
            match = self._match_exercise(text)
            if match:
                self._open_exercise(*match, pl)
                return
        elif current == "theory" and self.profile.lesson_level == "item" and self._starts_self_check(text):
            self._open_block("self_check", pl)
            self.block.title = "self_check"
            self._append_text(pl)
            return

        self._append_text(pl)

    def _starts_self_check(self, text: str) -> bool:
        """Мерзляк: після теорії йдуть питання «1. Як називають…» без заголовка."""
        return bool(re.match(r"^\W{0,2}1\s*\.\s+[А-ЯІЇЄҐ]", text)) and bool(self.block and self.block.text)

    def _two_line_heading(self, pl: PageLine, nxt: PageLine | None) -> bool:
        """Заголовок § / пункту, перенесений на два рядки («2. ЦИФРИ. Десятковий запис» +
        «натуральних чисел»). Пробуємо лише якщо перший рядок сам по собі не заголовок,
        а склеєний — так, і обидва рядки на одній сторінці."""
        if nxt is None or nxt.layout is not pl.layout or not _ITEM_PREFIX_RE.match(pl.text):
            return False
        if self._match_paragraph(pl.text) or self._match_item(pl.text):
            return False
        joined = f"{pl.text} {nxt.text}"
        entry = self._match_paragraph(joined)
        opener = self._open_paragraph
        if entry is None:
            entry, opener = self._match_item(joined), self._open_item
        if entry is None:
            return False
        opener(entry, pl)
        lesson = self.paragraph if opener == self._open_paragraph else self.item
        if lesson is not None:
            lesson.data["ocr_title"] = joined
            lesson.source = _extend_bbox(lesson.source, nxt)
        return True

    def parse(self, layouts: Iterable[PageLayout]) -> ParseResult:
        lines = list(iter_body_lines(layouts, self.profile.skip_pages))
        skip_next = False
        for i, pl in enumerate(lines):
            if skip_next:
                skip_next = False
                continue
            if self._two_line_heading(pl, lines[i + 1] if i + 1 < len(lines) else None):
                skip_next = True
                continue
            self.feed(pl)
        self._check_invariants()
        return ParseResult(self.root, self.issues, self.skipped_noise)

    # ------------------------------------------------------------------ перевірки

    def _check_invariants(self) -> None:
        """Самоперевірка дерева: порожні блоки, уроки без вправ, пропущені уроки зі змісту."""
        for lesson in self.root.find(self.profile.lesson_level):
            page = lesson.source.pdf_page if lesson.source else 0
            if not lesson.find("exercise"):
                self.issues.append(ParseIssue("lesson_without_exercises",
                                              f"Урок {lesson.number} без вправ", page, lesson.title))
            for block in lesson.children:
                if block.kind == "block" and not block.text and not block.children:
                    self.issues.append(ParseIssue("empty_block", f"Порожній блок {block.data.get('block_type')}",
                                                  page, lesson.title))


def parse_structure(profile: TextbookProfile, layouts: Iterable[PageLayout],
                    toc: Sequence[TocEntry] | None = None) -> ParseResult:
    """Зручна функція: профіль + розмічені сторінки → дерево і список проблем."""
    return StructureParser(profile, toc).parse(layouts)


def outline(node: Node, indent: int = 0, max_text: int = 60) -> str:
    """Текстове дерево для перевірки очима."""
    label = node.data.get("block_type") if node.kind == "block" else node.kind
    head = f"{'  ' * indent}{label}"
    if node.number:
        head += f" {node.number}"
    if node.kind == "exercise":
        head += f" [{node.data.get('difficulty')}]" + (" ⚠" if node.needs_review else "")
        head += f" {node.text.splitlines()[0][:max_text] if node.text else ''}"
    elif node.title and node.kind != "block":
        head += f" «{node.title[:max_text]}»"
    lines = [head]
    if node.kind != "exercise":
        lines += [outline(c, indent + 1, max_text) for c in node.children]
    return "\n".join(lines)
