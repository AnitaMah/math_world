"""Валідація дерева підручника (фаза 14): усі підозрілі місця одним списком.

Кожна перевірка — окрема маленька функція ``check_*``, що повертає ``list[Problem]``.
``validate`` збирає їх разом і сортує за важливістю. Перевірки нічого не змінюють
у дереві: вони лише показують, куди людині (або vision-LLM у фазі 15) варто подивитися.

Рівні важливості:
- ``error``   — дані майже напевно неправильні (дубль номера вправи, зламаний вираз);
- ``warning`` — ймовірна проблема (дірка в нумерації, назва пункту не як у змісті);
- ``info``    — варто глянути, але часто все гаразд (низька впевненість OCR).
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from ..datatypes import Node, SourceRef
from ..content.normalize import word_script

SEVERITIES = ("error", "warning", "info")
_SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}

LOW_CONF = 60.0            # середня впевненість рядка Tesseract (0–100)
TITLE_MIN_SCORE = 85.0     # як у структурному парсері
BLOCK_MAX_LINES = 90       # блок без вправ довший за ~2 сторінки — підозріло
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")

# Коди парсера, які дублюють власні перевірки дерева (там є ще й шлях до ноди).
DUPLICATED_PARSE_CODES = frozenset({"exercise_number_gap"})

# Коди проблем структурного парсера → важливість.
PARSE_ISSUE_SEVERITY = {
    "exercise_number_gap": "warning",
    "exercise_number_fixed": "info",
    "section_unknown": "warning",
    "item_without_paragraph": "warning",
    "block_without_lesson": "warning",
    "lesson_without_exercises": "warning",
    "empty_block": "warning",
}


@dataclass
class Problem:
    code: str
    severity: str
    message: str
    source: SourceRef | None = None
    node_path: str = ""
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in _SEVERITY_RANK:
            raise ValueError(f"severity={self.severity!r}; дозволені {SEVERITIES}")

    @property
    def pdf_page(self) -> int | None:
        return self.source.pdf_page if self.source else None

    def sort_key(self) -> tuple[int, int, str]:
        return (_SEVERITY_RANK[self.severity], self.pdf_page or 0, self.code)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "message": self.message,
                "source": self.source.to_dict() if self.source else None,
                "node_path": self.node_path, "text": self.text, "data": dict(self.data)}


# --------------------------------------------------------------------------- обхід з шляхом


def node_label(node: Node) -> str:
    if node.kind == "paragraph":
        return f"§{node.number}"
    if node.kind == "item":
        return f"п.{node.number}"
    if node.kind == "block":
        return str(node.data.get("block_type", "block"))
    if node.kind == "exercise":
        return f"№{node.number}"
    if node.kind == "subexercise":
        return f"{node.number})"
    if node.kind == "figure":
        return node.title or "рис."
    if node.kind == "section":
        return f"Розділ {node.number}"
    return node.kind


def walk_with_path(root: Node) -> Iterator[tuple[Node, list[Node]]]:
    """(нода, предки від кореня до батька)."""
    stack: list[tuple[Node, list[Node]]] = [(root, [])]
    while stack:
        node, parents = stack.pop()
        yield node, parents
        for child in reversed(node.children):
            stack.append((child, parents + [node]))


def path_str(node: Node, parents: Sequence[Node]) -> str:
    return " / ".join(node_label(n) for n in [*parents[1:], node])


def _nearest_source(node: Node, parents: Sequence[Node]) -> SourceRef | None:
    for n in [node, *reversed(parents)]:
        if n.source:
            return n.source
    return None


def _written_exercises(root: Node) -> list[tuple[Node, list[Node]]]:
    """Вправи письмових блоків (усні мають власну нумерацію в кожному пункті)."""
    return [(n, p) for n, p in walk_with_path(root)
            if n.kind == "exercise" and not any(a.data.get("block_type") == "oral_exercise" for a in p)]


def _int(number: str | None) -> int | None:
    return int(number) if number and number.isdigit() else None


# --------------------------------------------------------------------------- перевірки дерева


def check_empty_nodes(root: Node) -> list[Problem]:
    problems = []
    for node, parents in walk_with_path(root):
        if node.kind in ("textbook", "figure"):
            continue
        if not node.text.strip() and not node.children and not node.data.get("condition"):
            problems.append(Problem("empty_node", "warning", f"Порожня нода {node.kind}",
                                    _nearest_source(node, parents), path_str(node, parents)))
    return problems


def check_exercise_numbers(root: Node) -> list[Problem]:
    """Дірки (missing_exercise_number) і дублі (duplicate_exercise_number) у наскрізній нумерації."""
    problems = []
    seen: dict[int, Node] = {}
    previous: int | None = None
    for node, parents in _written_exercises(root):
        num = _int(node.number)
        if num is None:
            continue
        path = path_str(node, parents)
        if num in seen:
            problems.append(Problem("duplicate_exercise_number", "error", f"Номер {num} зустрічається двічі",
                                    node.source, path, node.text[:120]))
        elif previous is not None and num > previous + 1:
            missing = list(range(previous + 1, num))
            label = str(missing[0]) if len(missing) == 1 else f"{missing[0]}–{missing[-1]}"
            problems.append(Problem("missing_exercise_number", "warning",
                                    f"Немає вправ {label} (після {previous} одразу {num})",
                                    node.source, path, node.text[:120], {"missing": missing}))
        seen.setdefault(num, node)
        previous = max(previous or num, num)
    return problems


def check_item_titles(root: Node, min_score: float = TITLE_MIN_SCORE) -> list[Problem]:
    """Назва з OCR (data.ocr_title) суттєво відрізняється від назви зі змісту (title)."""
    problems = []
    for node, parents in walk_with_path(root):
        ocr = node.data.get("ocr_title")
        if node.kind not in ("section", "paragraph", "item") or not ocr or not node.title:
            continue
        score = fuzz.ratio(ocr.lower(), node.title.lower())
        if score < min_score:
            problems.append(Problem("item_title_mismatch", "warning",
                                    f"Назва з OCR «{ocr}» ≠ зміст «{node.title}» ({score:.0f}%)",
                                    node.source, path_str(node, parents), ocr, {"score": round(score, 1)}))
    return problems


def check_expressions(root: Node) -> list[Problem]:
    """Зламані (expr_malformed, error) і підозрілі (expr_suspect, info) вирази з фази 11."""
    problems = []
    for node, parents in walk_with_path(root):
        status = node.data.get("expr_status")
        if status not in ("malformed", "suspect"):
            continue
        issues = ", ".join(node.data.get("expr_issues", []))
        code, severity = ("expr_malformed", "error") if status == "malformed" else ("expr_suspect", "info")
        problems.append(Problem(code, severity, f"Вираз «{node.data.get('expr', node.text)}»: {issues}",
                                _nearest_source(node, parents), path_str(node, parents), node.text))
    return problems


def check_answer_mismatch(root: Node) -> list[Problem]:
    """Обчислена відповідь не збіглася з відповіддю книги (фаза 13)."""
    problems = []
    for node, parents in walk_with_path(root):
        if node.data.get("answer_mismatch"):
            problems.append(Problem(
                "answer_mismatch", "warning",
                f"Обчислено {node.data.get('answer')}, у книзі {node.data.get('answer_book')}",
                _nearest_source(node, parents), path_str(node, parents), node.text))
    return problems


def check_orphan_answers(root: Node, answer_numbers: Iterable[int]) -> list[Problem]:
    """Відповідь з книги, для якої немає вправи. Дивимось лише в межах номерів, що є в дереві
    (дерево може бути частиною книги, а відповіді — на всю книгу)."""
    numbers = {_int(n.number) for n, _ in _written_exercises(root)} - {None}
    if not numbers:
        return []
    lo, hi = min(numbers), max(numbers)
    return [Problem("orphan_answer", "warning", f"Є відповідь до №{num}, але такої вправи немає",
                    node_path=f"№{num}", data={"number": num})
            for num in sorted(set(answer_numbers)) if lo <= num <= hi and num not in numbers]


def check_figures(root: Node, figure_ids: Iterable[str] = ()) -> list[Problem]:
    """orphan_figure — рисунок знайдено, але не прив'язано ні до вправи, ні до уроку;
    missing_figure — вправа посилається на «рис. N», якого не знайшли."""
    problems = []
    in_tree = {n.data.get("figure_id") for n in root.find("figure")}
    for fid in figure_ids:
        if fid not in in_tree:
            problems.append(Problem("orphan_figure", "warning", f"Рисунок {fid} без прив'язки",
                                    node_path=fid, data={"figure_id": fid}))
    for node, parents in walk_with_path(root):
        for ref in node.data.get("missing_figures", []) if node.kind == "exercise" else []:
            problems.append(Problem("missing_figure", "warning", f"Вправа посилається на рис. {ref}, його не знайдено",
                                    node.source, path_str(node, parents), node.text[:120], {"figure": ref}))
    return problems


def mixed_words(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text) if word_script(w) == "mixed"]


def check_lookalikes(root: Node) -> list[Problem]:
    """Після нормалізації лишилися слова з латиницею і кирилицею водночас («cBoei»→«своєї» не спрацювало)."""
    problems = []
    for node, parents in walk_with_path(root):
        if node.kind not in ("block", "exercise", "subexercise"):
            continue
        text = node.data.get("condition") or node.text
        if text:
            words = mixed_words(text)
            if words:
                problems.append(Problem("lookalike_left", "warning", f"Мішані слова: {', '.join(words[:5])}",
                                        _nearest_source(node, parents), path_str(node, parents),
                                        text[:160], {"words": words}))
    return problems


def check_block_length(root: Node, max_lines: int = BLOCK_MAX_LINES) -> list[Problem]:
    """Блок без вправ (теорія, рубрики) підозріло довгий — ймовірно, пропущено маркер кінця."""
    problems = []
    for node, parents in walk_with_path(root):
        if node.kind != "block" or any(c.kind == "exercise" for c in node.children):
            continue
        count = len(node.data.get("line_keys", [])) or len(node.text.splitlines())
        if count > max_lines:
            problems.append(Problem("block_too_long", "warning",
                                    f"Блок {node.data.get('block_type')} має {count} рядків (> {max_lines})",
                                    _nearest_source(node, parents), path_str(node, parents),
                                    node.text[:120], {"lines": count}))
    return problems


def check_needs_review(root: Node) -> list[Problem]:
    """Ноди, які попередні фази позначили needs_review, але жодна перевірка вище не пояснила."""
    return [Problem("needs_review", "info", "Позначено needs_review", _nearest_source(n, p), path_str(n, p), n.text[:120])
            for n, p in walk_with_path(root) if n.needs_review]


# --------------------------------------------------------------------------- перевірки сторінок


def check_low_conf_lines(layouts: Iterable[Any], threshold: float = LOW_CONF) -> list[Problem]:
    problems = []
    for layout in layouts:
        for line in layout.body_lines:
            if line.words and line.conf < threshold:
                problems.append(Problem(
                    "low_conf_line", "info", f"Впевненість OCR {line.conf:.0f} < {threshold:.0f}",
                    SourceRef(layout.pdf_page, layout.book_page, line.bbox, (line.line_id,)),
                    f"стор. {layout.pdf_page}", line.text, {"conf": round(line.conf, 1)}))
    return problems


def check_pages_without_body(layouts: Iterable[Any], skip_pages: Iterable[int] = ()) -> list[Problem]:
    skip = set(skip_pages)
    return [Problem("page_without_body", "warning", "Сторінка без тексту тіла (OCR провалився або форзац?)",
                    SourceRef(lay.pdf_page, lay.book_page), f"стор. {lay.pdf_page}")
            for lay in layouts if lay.pdf_page not in skip and not any(ln.words for ln in lay.body_lines)]


def from_parse_issues(issues: Iterable[Any]) -> list[Problem]:
    """ParseIssue структурного парсера → Problem. Невідомий код = unknown_transition (warning)."""
    problems = []
    for issue in issues:
        if issue.code in DUPLICATED_PARSE_CODES:
            continue
        severity = PARSE_ISSUE_SEVERITY.get(issue.code)
        code = issue.code if severity else "unknown_transition"
        problems.append(Problem(code, severity or "warning", issue.message, SourceRef(issue.pdf_page),
                                f"стор. {issue.pdf_page}", issue.text, {"parser_code": issue.code}))
    return problems


# --------------------------------------------------------------------------- усе разом


def validate(root: Node, layouts: Sequence[Any] = (), parse_issues: Iterable[Any] = (),
             answer_numbers: Iterable[int] = (), figure_ids: Iterable[str] = (),
             skip_pages: Iterable[int] = ()) -> list[Problem]:
    problems = [
        *check_empty_nodes(root), *check_exercise_numbers(root), *check_item_titles(root),
        *check_expressions(root), *check_answer_mismatch(root), *check_orphan_answers(root, answer_numbers),
        *check_figures(root, figure_ids), *check_lookalikes(root), *check_block_length(root),
        *from_parse_issues(parse_issues),
        *check_low_conf_lines(layouts), *check_pages_without_body(layouts, skip_pages),
    ]
    explained = {(p.node_path) for p in problems}
    problems += [p for p in check_needs_review(root) if p.node_path not in explained]
    return sorted(problems, key=Problem.sort_key)


def count_by_code(problems: Iterable[Problem]) -> dict[str, int]:
    return dict(Counter(p.code for p in problems).most_common())


def tree_stats(root: Node) -> dict[str, int]:
    kinds = Counter(n.kind for n in root.walk())
    return {
        "paragraphs": kinds["paragraph"], "items": kinds["item"], "blocks": kinds["block"],
        "exercises": kinds["exercise"], "subexercises": kinds["subexercise"], "figures": kinds["figure"],
        "computed_answers": sum(1 for n in root.walk() if n.data.get("answer_source") == "computed"),
        "book_answers": sum(1 for n in root.walk() if "answer_book" in n.data or "answer_book_parts" in n.data),
        "verified": sum(1 for n in root.walk() if n.data.get("answer_verified")),
        "needs_review": sum(1 for n in root.walk() if n.needs_review),
    }
