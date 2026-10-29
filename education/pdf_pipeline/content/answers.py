"""Етап 10: розділ «ВІДПОВІДІ» → ключ відповідей і прив'язка до вправ.

Формат (Тарасенкова, стор. 287–299):

    § 26
    1122. 1) -6; 2) -4. 1124. 1) -4; 2) -98; 3) -16; ... 1150. Збільшилась на 5 учнів.

OCR склеює все підряд («13;23.16.1)29:37.17.1)7»), тому номер вправи визначаємо
обережно: «число + крапка», після якої йде пробіл, підпункт «1)» або літера,
і номери мусять зростати. Заголовки «§ 26» OCR читає як «826», «58», «8 34» —
приймаємо їх лише як короткий рядок з очікуваним наступним номером §.

Відповіді книги — найцінніше для гри: це **правильні** відповіді. А ще перевірка:
якщо наша автоматична відповідь (math_text) не збіглася з книжковою — OCR зламав вираз.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from ..datatypes import Line, Node
from ..layout import PageLayout

# Короткий рядок-заголовок параграфа: «§ 26», «§7», «826», «856», «8512», «58», «8 34», «§ 23 ЛЕП».
# OCR читає «§» як «8», «5», «85», «S», «$».
_PARAGRAPH_LINE_RE = re.compile(r"^\s*(?P<head>[§85S$]{1,2})\s?(?P<digits>\d{1,2})?(?:\s+\S{1,4})?\s*$")
_SIGN_VARIANTS = ("85", "§", "8", "5", "S", "$")
_SECTION_LINE_RE = re.compile(r"^\s*РОЗДІЛ\s+(\d)", re.IGNORECASE)
# Початок відповіді на вправу: «1122.» + (пробіл | «1)» | літера | мінус | дужка)
_EXERCISE_RE = re.compile(r"(?<![\d,])(\d{1,4})\.(?=\s|\d|[^\W\d_]|[(\-−–])")
# Підпункт усередині відповіді: «1)», «12)» — на початку або після «;», «.», пробілу
_SUBITEM_RE = re.compile(r"(?:(?<=^)|(?<=[;:.,\s]))(\d{1,2}|б)\)")   # «:» — OCR замість «;»
MAX_JUMP = 120            # між сусідніми відповідями бувають великі пропуски (не на всі вправи є відповідь)


@dataclass
class AnswerEntry:
    """Відповідь на одну вправу."""

    number: int
    paragraph: int | None
    pdf_page: int
    raw: str
    parts: dict[str, str] = field(default_factory=dict)    # "1" → "-6"; "" → відповідь без підпунктів

    def to_dict(self) -> dict[str, Any]:
        return {"number": self.number, "paragraph": self.paragraph, "pdf_page": self.pdf_page,
                "raw": self.raw, "parts": dict(self.parts)}


@dataclass
class AnswerKey:
    entries: dict[int, AnswerEntry] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    def get(self, number: int | str) -> AnswerEntry | None:
        try:
            return self.entries.get(int(number))
        except (TypeError, ValueError):
            return None


# --------------------------------------------------------------------------- очищення значень

_VALUE_FIXES = (
    (re.compile(r"\s*;\s*Рис\.\s*\d+$"), ""),          # «545 679; Рис. 224» — підпис сусіднього рисунка підклеївся
    (re.compile(r"(?<=\d)\s*:\s*(?=\d)"), "; "),       # «12: 16» — OCR «;» → «:»
    (re.compile(r"(?<![\w])б(?=\d|\b)"), "6"),          # «б0» → «60», «б)» уже оброблено
    (re.compile(r"(?<![\w])З(?=\s?\d|\b)"), "3"),       # «З дні» → «3 дні»
    (re.compile(r"(?<=[\s(;])-\s+(?=\d)"), "-"),        # «- 36» → «-36»
    (re.compile(r"^-\s+(?=\d)"), "-"),
)
_WORD_FIXES = {"Hi": "ні", "НІ": "ні", "Ні": "ні", "НІі": "ні", "Tak": "так", "Tax": "так", "Так": "так"}


def clean_value(text: str) -> str:
    """Прибирає типові помилки OCR у значенні відповіді і розділові знаки по краях."""
    value = text.strip().strip(";.,:").strip()
    for pattern, repl in _VALUE_FIXES:
        value = pattern.sub(repl, value)
    words = value.split()
    if words and words[0].strip(";.,") in _WORD_FIXES:
        words[0] = _WORD_FIXES[words[0].strip(";.,")]
        value = " ".join(words)
    return value


def split_parts(text: str) -> dict[str, str]:
    """«1) 4; 2) 98; 3) 16.» → {"1": "4", "2": "98", "3": "16"}; без підпунктів → {"": текст}."""
    matches = list(_SUBITEM_RE.finditer(text))
    if not matches:
        value = clean_value(text)
        return {"": value} if value else {}
    parts: dict[str, str] = {}
    head = text[: matches[0].start()].strip()
    if head:
        parts[""] = clean_value(head)
    for i, m in enumerate(matches):
        label = "6" if m.group(1) == "б" else m.group(1)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = clean_value(text[m.end():end])
        if value and label not in parts:
            parts[label] = value
    return parts


# --------------------------------------------------------------------------- розбір


def paragraph_marker(text: str, current: int | None) -> int | None:
    """Номер §, якщо рядок — заголовок «§ N» (з урахуванням помилок OCR) і N іде слідом за current."""
    compact = text.strip().split()
    token = "".join(compact[:2]) if len(compact) >= 2 and compact[1].isdigit() else (compact[0] if compact else "")
    for sign in _SIGN_VARIANTS:
        if token.startswith(sign) and token[len(sign):].isdigit():
            num = int(token[len(sign):])
            if current is None and num == 1 or current is not None and current < num <= current + 3:
                return num
    return None


def _best_chain(candidates: Sequence[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """Найдовший ланцюжок зростаючих номерів (кроки ≤ MAX_JUMP).

    Значення відповіді теж бувають «числом з крапкою» («3) 30. 12. 1)…»). Жадібний
    вибір узяв би 30 і пропустив 12, 15, 16…; найдовший ланцюжок (LIS) обирає
    послідовність, де вправ найбільше. При рівній довжині — менші сумарні стрибки.
    """
    n = len(candidates)
    best_len = [1] * n
    best_jump = [0] * n
    prev = [-1] * n
    for j in range(n):
        nj = candidates[j][0]
        for i in range(j):
            ni = candidates[i][0]
            if ni < nj <= ni + MAX_JUMP:
                length, jump = best_len[i] + 1, best_jump[i] + (nj - ni)
                if length > best_len[j] or (length == best_len[j] and jump < best_jump[j]):
                    best_len[j], best_jump[j], prev[j] = length, jump, i
    if not n:
        return []
    end = max(range(n), key=lambda k: (best_len[k], -best_jump[k]))
    chain = []
    while end != -1:
        chain.append(candidates[end])
        end = prev[end]
    return chain[::-1]


def parse_answer_lines(lines: Iterable[tuple[int, str]]) -> AnswerKey:
    """Рядки розділу відповідей (сторінка, текст) → ключ відповідей."""
    key = AnswerKey()
    paragraph: int | None = None
    stream: list[tuple[int, int | None, str]] = []      # (сторінка, §, шматок тексту)

    for page, text in lines:
        text = text.strip()
        if not text:
            continue
        m_sec = _SECTION_LINE_RE.match(text)
        if m_sec:
            continue
        found = paragraph_marker(text, paragraph) if len(text) <= 10 else None
        if found is not None:
            paragraph = found
            continue
        if len(text) <= 10 and _PARAGRAPH_LINE_RE.match(text):
            key.issues.append(f"стор. {page}: схоже на заголовок §, але номер не той, що очікували "
                              f"(§ {(paragraph or 0) + 1}): {text!r}")
            continue
        stream.append((page, paragraph, text))

    # Збираємо суцільний текст, пам'ятаючи, де починається кожен рядок (сторінка і §).
    full = ""
    marks: list[tuple[int, int, int | None]] = []        # (позиція в full, сторінка, §)
    for page, par, text in stream:
        marks.append((len(full), page, par))
        if full.endswith("-") and text[:1].isalpha():
            full = full[:-1]                              # перенос слова
        else:
            full += " " if full else ""
        full += text

    def where(pos: int) -> tuple[int, int | None]:
        page, par = marks[0][1], marks[0][2]
        for start, pg, pr in marks:
            if start > pos:
                break
            page, par = pg, pr
        return page, par

    candidates = [(int(m.group(1)), m.start(), m.end()) for m in _EXERCISE_RE.finditer(full)]
    starts = _best_chain([c for c in candidates if c[0] > 0])
    for i, (num, _start, end) in enumerate(starts):
        stop = starts[i + 1][1] if i + 1 < len(starts) else len(full)
        raw = full[end:stop].strip()
        page, par = where(end)
        key.entries[num] = AnswerEntry(num, par, page, raw, split_parts(raw))
    return key


def answer_lines_from_layouts(layouts: Iterable[PageLayout], pages: tuple[int, int]) -> list[tuple[int, str]]:
    first, last = pages
    result = []
    for layout in sorted(layouts, key=lambda lay: lay.pdf_page):
        if first <= layout.pdf_page <= last:
            result += [(layout.pdf_page, ln.text) for ln in layout.body_lines if ln.words]
    return result


# --------------------------------------------------------------------------- прив'язка до вправ

_NUMBER_RE = re.compile(r"^[−\-–]?\d+(?:[.,]\d+)?(?:/\d+)?$")


def to_number(text: str) -> Fraction | None:
    """«−3,5» → Fraction(-7, 2); «3/4» → 3/4; не число → None."""
    value = text.strip().replace(" ", "").replace("−", "-").replace("–", "-")
    if not _NUMBER_RE.match(value):
        return None
    value = value.replace(",", ".")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError):
        return None


@dataclass
class AttachStats:
    exercises_with_answers: int = 0
    parts_attached: int = 0
    verified: int = 0          # наша обчислена відповідь = книжковій
    mismatched: int = 0        # не збіглися → вираз зламаний OCR
    unknown_numbers: int = 0   # відповідь на вправу, якої немає в дереві


def attach_answers(root: Node, key: AnswerKey) -> AttachStats:
    """Записує книжкові відповіді у вправи/підпункти і звіряє з обчисленими."""
    stats = AttachStats()
    # Вправи з однаковим номером (усні у Мерзляка) не плутаємо: беремо лише письмові.
    exercises = {}
    for block in root.find("block"):
        if block.data.get("block_type") == "oral_exercise":
            continue
        for ex in block.children:
            if ex.kind == "exercise" and ex.number:
                exercises.setdefault(ex.number, ex)

    for number, entry in key.entries.items():
        ex = exercises.get(str(number))
        if ex is None:
            stats.unknown_numbers += 1
            continue
        stats.exercises_with_answers += 1
        ex.data["answer_book_raw"] = entry.raw
        subs = {s.number: s for s in ex.find("subexercise")}
        for label, value in entry.parts.items():
            target = subs.get(label) if label else None
            if target is None:
                if label:
                    ex.data.setdefault("answer_book_parts", {})[label] = value
                else:
                    ex.data["answer_book"] = value
                stats.parts_attached += 1
                continue
            target.data["answer_book"] = value
            stats.parts_attached += 1
            computed = target.data.get("answer")
            if computed is not None:
                a, b = to_number(computed), to_number(value)
                if a is not None and b is not None and a == b:
                    target.data["answer_verified"] = True
                    stats.verified += 1
                else:
                    target.data["answer_mismatch"] = True
                    target.needs_review = True
                    stats.mismatched += 1
    return stats


def summarize(key: AnswerKey) -> dict[str, Any]:
    numbers = sorted(key.entries)
    by_paragraph: dict[int | None, int] = {}
    for e in key.entries.values():
        by_paragraph[e.paragraph] = by_paragraph.get(e.paragraph, 0) + 1
    return {"answers": len(numbers), "first": numbers[0] if numbers else None,
            "last": numbers[-1] if numbers else None, "paragraphs": len([p for p in by_paragraph if p]),
            "issues": len(key.issues)}
