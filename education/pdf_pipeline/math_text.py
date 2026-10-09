"""Етап 8: математика у вправах — розбір виразів, безпечне обчислення, підозри, дроби.

Для гри найцінніші обчислювальні вправи: «1) 238 + 435;». Якщо вираз розпізнано
надійно, відповідь можна порахувати автоматично. Але OCR часто ламає саме
математику: «·» стає «-», «:», «°», «.» або зникає. Тому кожен вираз отримує статус:

* ``ok``          — вираз цілий, сумнівних знаків немає, відповідь правдоподібна → answer;
* ``suspect``     — вираз читається, але є підозрілий знак / дивна відповідь → на перевірку;
* ``malformed``   — дужки не збігаються, два знаки поспіль тощо;
* ``not_expression`` — це не вираз («6 і 24», «12 на 4») — для гри потрібна інша механіка.

Обчислення — власний маленький парсер на дробах (``fractions.Fraction``), **без eval**:
ніякий текст з PDF не може виконати код, а 1/3 + 1/3 + 1/3 дає рівно 1.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from fractions import Fraction

from .datatypes import BBox, Node

# --------------------------------------------------------------------------- токени

SUP_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
MAX_EXPONENT = 20
MINUS_CHARS = "−–—"
MUL_CHARS = "·×*∙"
DIV_CHARS = ":÷/"
SUSPECT_MUL = "°"            # OCR так читає «·»

_TOKEN_RE = re.compile(r"""
    (?P<grouped>\d{1,3}(?:[  ]\d{3})+(?![\d,]))   # 24 564 — число з пробілами-тисячами
  | (?P<number>\d+(?:,\d+)?)                          # 238, 3,5
  | (?P<sup>[⁰¹²³⁴⁵⁶⁷⁸⁹]+)                          # показник степеня з текстового шару: 26²
  | (?P<op>[+\-−–—·×*∙:÷/°])
  | (?P<lparen>[(\[])
  | (?P<rparen>[)\]])
  | (?P<dot>\.)                                        # крапка між числами — зламане «·»?
  | (?P<var>\b[a-zA-Z]\b)
  | (?P<word>[^\W\d_]+)
  | (?P<space>\s+)
  | (?P<other>.)
""", re.VERBOSE)


@dataclass(frozen=True)
class Token:
    kind: str           # number | op | lparen | rparen | var | word | other
    value: str          # нормалізоване: оператори → + - * /
    raw: str
    suspect: str = ""   # чому підозрілий ("" — ні)


def tokenize_expr(text: str, trusted_text: bool = False) -> list[Token]:
    """Розбиває вираз на токени і нормалізує знаки: −–— → «-», ·×* → «*», :÷ → «/».

    trusted_text — текст з вбудованого шару PDF (не OCR): «.» між операндами — це «·» множення,
    а не помилка розпізнавання, тож `dot_as_mul` не підозрілий; так само число з пробілами-тисячами
    («67 216») у шарі — одне число, а не два розірваних OCR, тож `grouped_number` не підозрілий."""
    tokens: list[Token] = []
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        raw = m.group()
        if kind == "space":
            continue
        if kind == "grouped":
            tokens.append(Token("number", raw.replace(" ", "").replace(" ", ""), raw,
                                suspect="" if trusted_text else "grouped_number"))
        elif kind == "number":
            tokens.append(Token("number", raw.replace(",", "."), raw))
        elif kind == "sup":
            tokens.append(Token("sup", raw, raw))
        elif kind == "op":
            if raw == "+":
                tokens.append(Token("op", "+", raw))
            elif raw in MINUS_CHARS:
                tokens.append(Token("op", "-", raw))
            elif raw == "-":
                # Після нормалізації справжній мінус — «−»; короткий дефіс між числами часто зламане «·».
                tokens.append(Token("op", "-", raw, suspect="hyphen_operator"))
            elif raw in MUL_CHARS:
                tokens.append(Token("op", "*", raw))
            elif raw == SUSPECT_MUL:
                tokens.append(Token("op", "*", raw, suspect="degree_as_mul"))
            elif raw in DIV_CHARS:
                tokens.append(Token("op", "/", raw))
        elif kind == "dot":
            tokens.append(Token("op", "*", raw, suspect="" if trusted_text else "dot_as_mul"))
        elif kind in ("lparen", "rparen"):
            tokens.append(Token(kind, "(" if kind == "lparen" else ")", raw))
        else:
            tokens.append(Token(kind, raw, raw))
    return tokens


# --------------------------------------------------------------------------- перевірка і обчислення


def check_tokens(tokens: list[Token]) -> list[str]:
    """Структурні помилки виразу (порожній список — вираз «правильної форми»)."""
    problems: list[str] = []
    depth = 0
    expect_operand = True
    for tok in tokens:
        if tok.kind in ("number", "var"):
            if not expect_operand:
                problems.append("missing_operator")      # «24 564» без знака, «12:5-4 1»
            expect_operand = False
        elif tok.kind == "sup":
            if expect_operand:
                problems.append("stray_superscript")     # степінь без основи: «+ ²»
        elif tok.kind == "op":
            if expect_operand:
                problems.append("double_operator")       # «43--24»
            expect_operand = True
        elif tok.kind == "lparen":
            if not expect_operand:
                problems.append("missing_operator")
            depth += 1
        elif tok.kind == "rparen":
            depth -= 1
            if depth < 0 or expect_operand:
                problems.append("bad_parentheses")
                depth = max(depth, 0)
        else:
            problems.append(f"unexpected_{tok.kind}")
    if depth != 0:
        problems.append("bad_parentheses")
    if tokens and expect_operand:
        problems.append("dangling_operator")
    if not tokens:
        problems.append("empty")
    return sorted(set(problems))


class _Parser:
    """Рекурсивний спуск: expr = term (± term)* ; term = factor (*/ factor)* ; factor = число | (expr)."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expr(self) -> Fraction:
        value = self.term()
        while (tok := self.peek()) and tok.kind == "op" and tok.value in "+-":
            self.take()
            right = self.term()
            value = value + right if tok.value == "+" else value - right
        return value

    def term(self) -> Fraction:
        value = self.factor()
        while (tok := self.peek()) and tok.kind == "op" and tok.value in "*/":
            self.take()
            right = self.factor()
            if tok.value == "*":
                value *= right
            else:
                if right == 0:
                    raise ValueError("ділення на нуль")
                value /= right
        return value

    def factor(self) -> Fraction:
        value = self.primary()
        while (tok := self.peek()) and tok.kind == "sup":
            self.take()
            exponent = int(tok.value.translate(SUP_DIGITS))
            if exponent > MAX_EXPONENT:
                raise ValueError("завеликий показник степеня")
            value = value ** exponent
        return value

    def primary(self) -> Fraction:
        tok = self.peek()
        if tok is None:
            raise ValueError("вираз обірвався")
        if tok.kind == "number":
            self.take()
            return Fraction(tok.value)
        if tok.kind == "lparen":
            self.take()
            value = self.expr()
            if not (self.peek() and self.peek().kind == "rparen"):
                raise ValueError("немає закривної дужки")
            self.take()
            return value
        raise ValueError(f"неочікуваний токен {tok.raw!r}")


def safe_eval(text: str) -> Fraction:
    """Обчислює арифметичний вираз з книги. Лише числа, + − · : і дужки; інакше ValueError."""
    tokens = tokenize_expr(text)
    problems = check_tokens(tokens)
    if problems:
        raise ValueError(f"некоректний вираз: {', '.join(problems)}")
    parser = _Parser(tokens)
    value = parser.expr()
    if parser.pos != len(tokens):
        raise ValueError("зайві токени в кінці виразу")
    return value


def format_answer(value: Fraction) -> str:
    """17 → «17»; 7/2 → «7/2»; від'ємні з мінусом «−»."""
    sign = "−" if value < 0 else ""
    value = abs(value)
    return f"{sign}{value.numerator}" if value.denominator == 1 else f"{sign}{value.numerator}/{value.denominator}"


# --------------------------------------------------------------------------- аналіз підпункту


@dataclass
class ExprResult:
    status: str                      # ok | suspect | malformed | not_expression
    expression: str                  # нормалізований запис («238 + 435»)
    value: Fraction | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def answer(self) -> str | None:
        return format_answer(self.value) if self.value is not None and self.status == "ok" else None


_TRAILING_RE = re.compile(r"[\s;.,?!]+$")              # «238 + 435;» → «238 + 435»
_LEADING_RE = re.compile(r"^[^\d(\[a-zA-Zа-яА-ЯіїєґІЇЄҐ]+")   # сміття перед виразом
_PRETTY = {"+": "+", "-": "−", "*": "·", "/": ":"}


def analyze_expression(text: str, natural_numbers: bool = True, trusted_text: bool = False) -> ExprResult:
    """Аналізує текст підпункту як арифметичний вираз.

    natural_numbers — книга про натуральні числа (5 клас): дробова чи від'ємна
    відповідь там майже напевно означає зламаний знак (напр. «98 : 34» замість «98 · 34»).
    """
    core = _LEADING_RE.sub("", _TRAILING_RE.sub("", text.strip()))
    tokens = tokenize_expr(core, trusted_text)
    if any(t.kind == "word" for t in tokens) or not any(t.kind == "op" for t in tokens):
        return ExprResult("not_expression", core)
    if any(t.kind == "var" for t in tokens):
        return ExprResult("not_expression", core, issues=["has_variable"])

    pretty = ""
    for t in tokens:
        piece = _PRETTY.get(t.value, t.value) if t.kind == "op" else t.value
        pretty += piece if t.kind == "sup" or not pretty else " " + piece
    pretty = pretty.replace("( ", "(").replace(" )", ")")
    problems = check_tokens(tokens)
    if problems:
        return ExprResult("malformed", pretty, issues=problems)

    issues = sorted({t.suspect for t in tokens if t.suspect})
    try:
        value = safe_eval(core)
    except ValueError as exc:
        return ExprResult("malformed", pretty, issues=[str(exc)])
    if natural_numbers and (value.denominator != 1 or value < 0):
        issues.append("implausible_result")
    return ExprResult("suspect" if issues else "ok", pretty, value, issues)


# --------------------------------------------------------------------------- дроби на картинці


def detect_fraction_bars(image, text_height: int | None = None, top_ignore: float = 0.11) -> list[BBox]:
    """Двоповерхові дроби: окрема тонка горизонтальна риска з цифрами і над, і під нею.

    Чим риска дробу відрізняється від схожого:
    * від горизонтальних штрихів літер («т», «5», «7») — вона **окрема пляма**
      (компонента зв'язності), а штрих букви з'єднаний з рештою букви;
    * від мінуса — над і під мінусом порожньо;
    * від знака «=» — над нижньою рискою «=» лише інша тонка риска, а не цифра
      (вимагаємо, щоб чорнило зверху/знизу займало кілька рядків пікселів).
    text_height — орієнтовна висота рядка в пікселях (None — ≈1.35% висоти сторінки:
    18 px у Мерзляка, 24 px у Тарасенкової). top_ignore — смуга колонтитула з декором.
    """
    import cv2
    import numpy as np
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    h_img = gray.shape[0]
    if text_height is None:
        text_height = max(round(h_img * 0.0135), 8)
    min_len = max(text_height // 2, 6)
    reach = int(text_height * 1.1)
    min_rows = max(int(text_height * 0.35), 3)
    bars: list[BBox] = []
    for i in range(1, count):
        x, y, w, h, _area = stats[i]
        if h > 4 or w < min_len or w > text_height * 5 or w < 4 * h or y < h_img * top_ignore:
            continue
        others = (labels != i) & (labels != 0)
        above = others[max(y - reach, 0):y, x:x + w]
        below = others[y + h:min(y + h + reach, h_img), x:x + w]
        if above.any(axis=1).sum() >= min_rows and below.any(axis=1).sum() >= min_rows:
            bars.append(BBox(int(x), int(max(y - reach, 0)), int(x + w), int(min(y + h + reach, h_img))))
    return sorted(bars, key=lambda b: (b.y0, b.x0))


# --------------------------------------------------------------------------- по дереву


@dataclass
class MathStats:
    expressions: int = 0
    ok: int = 0
    suspect: int = 0
    malformed: int = 0
    not_expression: int = 0
    with_fractions: int = 0


def enrich_math(root: Node, natural_numbers: bool = True,
                fraction_bars: dict[int, list[BBox]] | None = None, trusted_text: bool = False) -> MathStats:
    """Для підпунктів обчислювальних вправ: вираз, статус, автоматична відповідь.

    fraction_bars — {сторінка: [дроби]} з detect_fraction_bars; вправа, у рамці якої
    є дріб, отримує has_fractions і needs_review (OCR дроби не читає → vision).
    """
    stats = MathStats()
    for ex in root.find("exercise"):
        if fraction_bars and ex.source and ex.source.bbox:
            bars = fraction_bars.get(ex.source.pdf_page, [])
            if any(b.intersects(ex.source.bbox) for b in bars):
                ex.data["has_fractions"] = True
                ex.needs_review = True
                stats.with_fractions += 1
        if ex.data.get("task_verb") not in ("compute",):
            continue
        for sub in ex.find("subexercise"):
            result = analyze_expression(sub.text, natural_numbers=natural_numbers, trusted_text=trusted_text)
            stats.expressions += 1
            setattr(stats, result.status, getattr(stats, result.status) + 1)
            sub.data["expr"] = result.expression
            sub.data["expr_status"] = result.status
            if result.issues:
                sub.data["expr_issues"] = result.issues
            if result.answer is not None:
                sub.data["answer"] = result.answer
                sub.data["answer_source"] = "computed"
            if result.status in ("suspect", "malformed"):
                sub.needs_review = True
    return stats


def iter_compute_subexercises(root: Node) -> Iterable[Node]:
    for ex in root.find("exercise"):
        if ex.data.get("task_verb") == "compute":
            yield from ex.find("subexercise")
