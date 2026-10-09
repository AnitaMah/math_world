"""Профіль підручника: усе, що специфічне для конкретної книги, — у даних, а не в коді.

Структурний парсер (фаза 9) спільний для всіх книг. Він питає в профілю:
«цей рядок — заголовок §? рубрика? початок вправи? яка в неї складність?».
Новий підручник = новий файл профілю, а не правки в парсері.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Pattern

from rapidfuzz import fuzz

# Єдина шкала складності для всіх книг (кожна книга має свої значки — див. профілі).
DIFFICULTY_LEVELS = ("preparatory", "medium", "sufficient", "high", "olympiad")

_APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'", "`": "'", "‘": "'"})
_LAT_TO_CYR = str.maketrans("aeopcxyiABCEHKMOPTXI", "аеорсхуіАВСЕНКМОРТХІ")
_NOT_WORD = re.compile(r"[^\w' ]+")
_SPACES = re.compile(r"\s+")


def normalize_marker_text(text: str) -> str:
    """Текст для порівняння з маркером: малі літери, без розділових знаків і зайвих пробілів.

    «РОЗВ’ЯЖІТЬ  ЗАДАЧІ» і «Розв'яжіть задачі:» → «розв'яжіть задачі».
    Латинські двійники теж → кирилиця, бо маркер міг прийти до нормалізації.
    """
    text = text.translate(_APOSTROPHES).translate(_LAT_TO_CYR).lower()
    text = _NOT_WORD.sub(" ", text)
    return " ".join(_join_spaced_letters(text.split()))


def _join_spaced_letters(tokens: list[str]) -> list[str]:
    """«з а д а ч а» (рубрика надрукована врозрядку) → «задача». Склеюємо 3+ однолітерні токени поспіль."""
    out: list[str] = []
    run: list[str] = []
    for tok in tokens + [""]:
        if len(tok) == 1 and tok.isalpha():
            run.append(tok)
            continue
        if len(run) >= 3:
            out.append("".join(run))
        else:
            out.extend(run)
        run = []
        if tok:
            out.append(tok)
    return out


@dataclass(frozen=True)
class BlockMarker:
    """Рубрика підручника, з якої починається блок певного типу.

    phrases    — варіанти написання (порівнюються після normalize_marker_text);
    threshold  — мінімальна схожість 0–100 (OCR-помилки в 1–2 літери проходять);
    whole_line — рубрика займає весь рядок (заголовок). Якщо False — достатньо,
                 щоб рядок **починався** з фрази («Задача. Знайдіть…»).
    """

    block_type: str
    phrases: tuple[str, ...]
    threshold: int = 85
    whole_line: bool = True

    def score(self, line_text: str) -> float:
        """Наскільки рядок схожий на цю рубрику (0–100)."""
        text = normalize_marker_text(line_text)
        if not text:
            return 0.0
        best = 0.0
        for phrase in self.phrases:
            target = normalize_marker_text(phrase)
            if self.whole_line:
                score = fuzz.ratio(text, target)
            else:
                score = fuzz.ratio(text[: len(target)], target)
            best = max(best, score)
        return best


@dataclass(frozen=True)
class TocEntry:
    """Рядок змісту: розділ / параграф / пункт."""

    kind: str           # "section" | "paragraph" | "item"
    number: str
    title: str


_TOC_SECTION = re.compile(r"^Розділ\s+(?P<num>[IVX]+|\d+)\.?\s*(?P<title>.*)$")
_TOC_PARAGRAPH = re.compile(r"^§\s*(?P<num>\d+)\.\s*(?P<title>.+)$")
_TOC_ITEM = re.compile(r"^(?P<num>\d+)\.\s+(?P<title>.+)$")


def load_toc(path: str | Path) -> list[TocEntry]:
    """Читає текстовий зміст (data/5_class_ukr.txt) у список записів. Інші рядки пропускає."""
    entries: list[TocEntry] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        for kind, pattern in (("section", _TOC_SECTION), ("paragraph", _TOC_PARAGRAPH), ("item", _TOC_ITEM)):
            m = pattern.match(line)
            if m:
                entries.append(TocEntry(kind, m.group("num"), m.group("title").strip()))
                break
    return entries


@dataclass(frozen=True)
class TextbookProfile:
    """Опис одного підручника для парсера."""

    code: str                       # "math_merzlyak_5"
    subject_code: str               # "math"
    grade: int
    author: str
    year: int
    title: str
    pdf_name: str                   # ім'я PDF-файлу в корені проєкту

    lesson_level: str               # де «урок» гри: "item" (пункт, Мерзляк) або "paragraph" (§, Тарасенкова)
    section_re: Pattern[str]
    paragraph_re: Pattern[str]
    item_re: Pattern[str] | None    # None — у книзі немає пунктів усередині §
    exercise_re: Pattern[str]       # групи: num, mark, rest
    block_markers: tuple[BlockMarker, ...]
    difficulty_marks: dict[str, str]   # значок → рівень з DIFFICULTY_LEVELS
    default_difficulty: str | None     # рівень вправи без значка
    homework_marker: str | None = None  # "colored_number" | "margin_icon" | None
    difficulty_from_image: bool = False  # значок складності шукати на картинці (OCR його губить)

    toc_path: str | None = None
    skip_pages: frozenset[int] = frozenset()      # обкладинка, передмова, зміст…
    answers_pages: tuple[int, int] | None = None  # (перша, остання) сторінка PDF з відповідями
    ocr_engine: str = "tesseract"       # "tesseract" або "pdftext" (вбудований текстовий шар PDF)
    header_band: float = 0.11
    footer_band: float = 0.06
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for symbol, level in self.difficulty_marks.items():
            if level not in DIFFICULTY_LEVELS:
                raise ValueError(f"{self.code}: невідомий рівень {level!r} для значка {symbol!r}")
        if self.default_difficulty not in (None, *DIFFICULTY_LEVELS):
            raise ValueError(f"{self.code}: невідомий default_difficulty {self.default_difficulty!r}")
        if self.lesson_level not in ("item", "paragraph"):
            raise ValueError(f"{self.code}: lesson_level має бути 'item' або 'paragraph'")

    # ------------------------------------------------------------------ запитання парсера

    def match_block_marker(self, line_text: str) -> tuple[BlockMarker, float] | None:
        """Найкраща рубрика для рядка (і її схожість) або None.

        При однаковій схожості перемагає довша фраза: «Вправи для повторення» важливіша
        за «Вправи».
        """
        best: tuple[BlockMarker, float] | None = None
        for marker in self.block_markers:
            score = marker.score(line_text)
            if score < marker.threshold:
                continue
            longest = max(len(p) for p in marker.phrases)
            if best is None or (score, longest) > (best[1], max(len(p) for p in best[0].phrases)):
                best = (marker, score)
        return best

    def parse_exercise_start(self, line_text: str) -> tuple[int, str | None, str] | None:
        """«40°. Із чисел…» → (40, "medium", "Із чисел…"); не початок вправи → None.

        Рівень: значок → difficulty_marks; без значка → default_difficulty;
        невідомий значок → "unknown" (парсер позначить needs_review).
        """
        m = self.exercise_re.match(line_text.strip())
        if not m:
            return None
        mark = (m.group("mark") or "").strip()
        if mark:
            level = self.difficulty_marks.get(mark, "unknown")
        else:
            level = self.default_difficulty
        return int(m.group("num")), level, m.group("rest").strip()

    def toc(self) -> list[TocEntry]:
        return load_toc(self.toc_path) if self.toc_path else []

    def lesson_titles(self) -> list[TocEntry]:
        """Записи змісту, що є «уроками» (пункти або параграфи — залежно від lesson_level)."""
        return [e for e in self.toc() if e.kind == self.lesson_level]


def roman_to_int(text: str) -> int:
    """«IV» → 4. Помилка на некоректне римське число."""
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
    text = text.upper().strip()
    if not text or any(ch not in values for ch in text) or not re.fullmatch(r"C{0,3}(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", text):
        raise ValueError(f"Не римське число: {text!r}")
    total = 0
    for ch, nxt in zip(text, text[1:] + " "):
        v = values[ch]
        total += -v if nxt != " " and values[nxt] > v else v
    return total


def section_number(raw: str) -> int:
    """Номер розділу: «II» → 2, «3» → 3."""
    return int(raw) if raw.isdigit() else roman_to_int(raw)


def all_phrases(markers: Iterable[BlockMarker]) -> list[str]:
    return [p for m in markers for p in m.phrases]
