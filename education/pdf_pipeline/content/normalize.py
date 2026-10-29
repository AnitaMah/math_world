"""Етап 5: нормалізація тексту після OCR.

Виправляємо **систематичні** помилки, які не змінюють зміст:
латинські двійники в українських словах (``Ha`` → ``на``), різні апострофи,
тире між словами, перенос слів між рядками. Математику **не вгадуємо**:
підозрілі знаки лише позначаємо прапорцем ``suspect_operator``.

Кожне правило — окрема функція ``(слово, контекст) → новий текст або None``.
``Normalizer`` застосовує їх по черзі, рахує спрацювання і дозволяє
вимкнути будь-яке правило за назвою. Оригінальний текст слова зберігається
в ``Word.raw_text``, координати не змінюються.
"""
from __future__ import annotations

import dataclasses
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from ..datatypes import BBox, Line, Word

# --------------------------------------------------------------------------- таблиці

# Латинська літера → кириличний двійник (вигляд однаковий у більшості шрифтів).
LATIN_TO_CYR: dict[str, str] = {
    "a": "а", "e": "е", "o": "о", "p": "р", "c": "с", "x": "х", "y": "у", "i": "і",
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К", "M": "М",
    "O": "О", "P": "Р", "T": "Т", "X": "Х", "I": "І",
    "h": "ь",   # у шрифті підручника «ь» схожий на «h»: «Bech» = «весь»
}

# Явні виправлення частих слів, які не вкладаються в загальні правила.
KNOWN_WORD_FIXES: dict[str, str] = {
    "3a": "за", "3а": "за",       # цифра 3 замість «з»
}

# Слова, після яких одна латинська літера — математична змінна («буквою a»).
VARIABLE_CONTEXT = {"буквою", "число", "числа", "числу", "змінна", "змінної", "змінну", "позначили"}
# Слова-підказки, що поруч геометричні позначення (AB, CD — латиниця за правилами).
GEOMETRY_CONTEXT = {"відрізок", "відрізка", "відрізку", "пряма", "прямої", "пряму", "промінь",
                    "променя", "трикутник", "трикутника", "точка", "точки", "кут", "кута", "ламана", "ламаної"}
# Перша частина справжнього дефіса: «будь-який» лишається з дефісом.
REAL_HYPHEN_PREFIXES = {"будь", "казна", "хтозна", "абияк", "де", "сяк", "що", "як", "по"}
REAL_HYPHEN_SUFFIXES = {"небудь", "то", "таки", "от"}

APOSTROPHES = "’ʼ‘`´"
CANON_APOSTROPHE = "'"
MINUS = "−"

_CYR_RE = re.compile(r"[а-щьюяєіїґА-ЩЬЮЯЄІЇҐ]")
_LAT_RE = re.compile(r"[A-Za-z]")
_ROMAN_RE = re.compile(r"^[IVXLC]+\.?$")
_NUMBERISH_RE = re.compile(r"^[\(\[]?\d[\d\s,.]*[\)\]]?[;:,.?]?$")
_SENTENCE_END = (".", "!", "?", ":")
_PUNCT = ".,;:!?»«)(\"'"


# --------------------------------------------------------------------------- контекст


@dataclass(frozen=True)
class Context:
    """Сусіди слова в рядку — щоб правила могли дивитися навколо."""

    prev: str | None
    next: str | None

    @property
    def prev_lower(self) -> str:
        return (self.prev or "").strip(_PUNCT).lower()

    @property
    def mid_sentence(self) -> bool:
        return self.prev is not None and not self.prev.endswith(_SENTENCE_END)


def word_script(word: str) -> str:
    """'cyr' | 'lat' | 'mixed' | 'other' — за літерами слова."""
    cyr, lat = bool(_CYR_RE.search(word)), bool(_LAT_RE.search(word))
    if cyr and lat:
        return "mixed"
    return "cyr" if cyr else "lat" if lat else "other"


def _is_numberish(text: str | None) -> bool:
    return bool(text) and bool(_NUMBERISH_RE.match(text))


def _is_math_neighbor(text: str | None) -> bool:
    return _is_numberish(text) or (text or "") in {"+", "-", "−", "—", "–", "=", ":", "·", "×", "<", ">"}


_VOWELS = set("аеєиіїоуюяАЕЄИІЇОУЮЯ")
_IOTATED = {"е": "є", "і": "ї", "Е": "Є", "І": "Ї"}


def _map_latin(word: str) -> str:
    """Латинські двійники → кирилиця. Латинські «e»/«i» не розрізняють «е/є» та «і/ї»;
    після голосної в українському слові майже завжди «є»/«ї» («cBoei» → «своєї»)."""
    out: list[str] = []
    for ch in word:
        cyr = LATIN_TO_CYR.get(ch, ch)
        if ch != cyr and cyr in _IOTATED and out and out[-1] in _VOWELS:
            cyr = _IOTATED[cyr]
        out.append(cyr)
    return "".join(out)


# --------------------------------------------------------------------------- правила


def rule_apostrophe(word: str, ctx: Context) -> str | None:
    """Усі види апострофів → один (щоб «Розв’язуємо» і «Розв'язуємо» шукалися однаково)."""
    if any(a in word for a in APOSTROPHES):
        return "".join(CANON_APOSTROPHE if ch in APOSTROPHES else ch for ch in word)
    return None


def rule_known_words(word: str, ctx: Context) -> str | None:
    core = word.strip(_PUNCT)
    if core in KNOWN_WORD_FIXES:
        return word.replace(core, KNOWN_WORD_FIXES[core])
    return None


def rule_mixed_script(word: str, ctx: Context) -> str | None:
    """Кирилиця + латиниця в одному слові («Bправи», «нaтуральний») → уся кирилиця."""
    if word_script(word) != "mixed":
        return None
    latin = [ch for ch in word if _LAT_RE.match(ch)]
    if not all(ch in LATIN_TO_CYR for ch in latin):
        return None            # є латинська літера без двійника — не чіпаємо
    fixed = _map_latin(word)
    return fixed[0] + fixed[1:].lower() if fixed[:1].isupper() else fixed.lower()


def rule_latin_lookalike_word(word: str, ctx: Context) -> str | None:
    """Ціле латинське слово з самих «двійників» серед українського тексту («Ha» → «на»).

    Не чіпаємо: римські числа (I, IV), змінні після «буквою»/поруч із числами,
    геометричні позначення (AB після «відрізок»).
    """
    core = word.strip(_PUNCT)
    if not core or word_script(core) != "lat" or not all(ch in LATIN_TO_CYR for ch in core):
        return None
    if _ROMAN_RE.match(core):
        return None
    # Змінні в підручнику — малі латинські (a, x, n). Велика «B» після «число» — це прийменник «в».
    if len(core) == 1 and core.islower() and (ctx.prev_lower in VARIABLE_CONTEXT
                                              or _is_math_neighbor(ctx.prev) or _is_math_neighbor(ctx.next)):
        return None
    if core.isupper() and len(core) <= 3 and ctx.prev_lower in GEOMETRY_CONTEXT:
        return None
    if core.isupper() and len(core) >= 2 and not ctx.mid_sentence and ctx.prev is not None:
        return None            # абревіатура на початку речення — обережно, лишаємо
    fixed = _map_latin(core)
    # «Ha», «Bech» посеред речення — це малі літери, просто шрифт схожий на великі.
    if ctx.mid_sentence:
        fixed = fixed.lower()
    elif len(fixed) > 1:
        fixed = fixed[0] + fixed[1:].lower()
    return word.replace(core, fixed)


def rule_word_dash(word: str, ctx: Context) -> str | None:
    """Тире між словами: «--», «-», «–» → «—» (але не між числами — там це математика)."""
    if word not in {"--", "-", "–", "—"} or word == "—":
        return None
    if _is_math_neighbor(ctx.prev) or _is_math_neighbor(ctx.next):
        return None
    return "—"


def rule_minus_between_numbers(word: str, ctx: Context) -> str | None:
    """Довге тире між числами — це мінус: «2000 — 546» → «2000 − 546».

    (Короткий дефіс «-» між числами OCR дає замість «·» — його не вгадуємо, див. flag_suspect_operator.)
    """
    if word in {"—", "–", "--"} and _is_math_neighbor(ctx.prev) and _is_math_neighbor(ctx.next):
        return MINUS
    return None


def flag_suspect_operator(word: str, ctx: Context) -> str | None:
    """Прапорець, а не заміна: «-» між числами часто є зламаним «·» (множенням)."""
    if word == "-" and _is_math_neighbor(ctx.prev) and _is_math_neighbor(ctx.next):
        return "suspect_operator"
    return None


Rule = Callable[[str, Context], "str | None"]

DEFAULT_RULES: tuple[tuple[str, Rule], ...] = (
    ("apostrophe", rule_apostrophe),
    ("known_words", rule_known_words),
    ("mixed_script", rule_mixed_script),
    ("latin_lookalike_word", rule_latin_lookalike_word),
    ("minus_between_numbers", rule_minus_between_numbers),
    ("word_dash", rule_word_dash),
)
DEFAULT_FLAGS: tuple[tuple[str, Rule], ...] = (
    ("suspect_operator", flag_suspect_operator),
)


# --------------------------------------------------------------------------- переноси


def join_hyphenation(lines: Sequence[Line]) -> int:
    """Склеює перенесені слова: «натураль-» + «них» → «натуральних» (змінює рядки на місці).

    Склеєне слово лишається в першому рядку (bbox — об'єднання частин), а друга
    частина зникає з початку наступного. «будь-» + «який» → «будь-який» (дефіс справжній).
    Повертає кількість склеювань.
    """
    joined = 0
    for line, nxt in zip(lines, lines[1:]):
        if not line.words or not nxt.words:
            continue
        last, first = line.words[-1], nxt.words[0]
        if not (last.text.endswith("-") and len(last.text) > 1 and last.text[-2].isalpha()):
            continue
        if not first.text[:1].isalpha() or not first.text[:1].islower():
            continue
        head = last.text[:-1]
        keep_dash = head.lower() in REAL_HYPHEN_PREFIXES or first.text.strip(_PUNCT).lower() in REAL_HYPHEN_SUFFIXES
        merged_text = f"{head}-{first.text}" if keep_dash else head + first.text
        line.words[-1] = dataclasses.replace(
            last, text=merged_text, bbox=last.bbox.union(first.bbox),
            raw_text=f"{last.raw_text or last.text}|{first.raw_text or first.text}",
        )
        nxt.words.pop(0)
        joined += 1
    return joined


# --------------------------------------------------------------------------- конвеєр


@dataclass
class Normalizer:
    """Застосовує правила до слів рядків. ``disabled`` — назви правил, які пропустити."""

    rules: tuple[tuple[str, Rule], ...] = DEFAULT_RULES
    flag_rules: tuple[tuple[str, Rule], ...] = DEFAULT_FLAGS
    disabled: frozenset[str] = frozenset()
    join_hyphens: bool = True
    stats: Counter[str] = field(default_factory=Counter)

    def normalize_word(self, word: Word, ctx: Context) -> Word:
        text = word.text
        for name, rule in self.rules:
            if name in self.disabled:
                continue
            new = rule(text, ctx)
            if new is not None and new != text:
                self.stats[name] += 1
                text = new
        flags = list(word.flags)
        for name, rule in self.flag_rules:
            if name not in self.disabled and (flag := rule(text, ctx)) and flag not in flags:
                self.stats[name] += 1
                flags.append(flag)
        if text == word.text and tuple(flags) == word.flags:
            return word
        raw = word.raw_text if word.raw_text is not None else (word.text if text != word.text else None)
        return dataclasses.replace(word, text=text, raw_text=raw, flags=tuple(flags))

    def normalize_line(self, line: Line) -> Line:
        texts = [w.text for w in line.words]
        new_words = [
            self.normalize_word(w, Context(texts[i - 1] if i else None, texts[i + 1] if i + 1 < len(texts) else None))
            for i, w in enumerate(line.words)
        ]
        return dataclasses.replace(line, words=new_words)

    def normalize_lines(self, lines: Iterable[Line]) -> list[Line]:
        """Нові рядки (оригінальні не змінюються) + склеєні переноси."""
        result = [self.normalize_line(ln) for ln in lines]
        if self.join_hyphens and "hyphenation" not in self.disabled:
            self.stats["hyphenation"] += join_hyphenation(result)
            result = [ln for ln in result if ln.words]
        return result


def normalize_lines(lines: Iterable[Line], disabled: Iterable[str] = ()) -> tuple[list[Line], Counter[str]]:
    """Зручна функція: (нормалізовані рядки, скільки разів спрацювало кожне правило)."""
    normalizer = Normalizer(disabled=frozenset(disabled))
    return normalizer.normalize_lines(lines), normalizer.stats
