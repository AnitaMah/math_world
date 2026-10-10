"""Експорт дерева в JSON-контракт (фаза 16) і завантаження назад.

``export_textbook`` перетворює внутрішнє дерево ``Node`` на формат зі ``schema.py``:
- службові поля пайплайну (``line_keys``, ``raw`` тощо) не потрапляють назовні;
- рисунки — один список ``figures`` верхнього рівня, з вправ/блоків на них посилаються ``figure_ids``;
- відповіді вправи і підпункту зведені в один об'єкт ``answer`` {computed, book, verified, mismatch};
- результат перевіряється схемою **перед** записом (неправильний файл просто не з'явиться).

Детермінованість: порядок усього визначає дерево, числа округлені, ключі в сталому порядку,
тож два прогони на тих самих даних дають однаковий JSON (відрізняється лише ``meta.created_at``).
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .datatypes import Node, SourceRef
from .schema import SCHEMA_VERSION, SchemaError, validate_textbook

EXERCISE_FLAGS = ("number_fixed", "difficulty_suspicious", "has_fractions")


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _source(src: SourceRef | None) -> dict[str, Any] | None:
    if src is None:
        return None
    return {"pdf_page": src.pdf_page, "book_page": src.book_page,
            "bbox": src.bbox.to_dict() if src.bbox else None}


def _put(out: dict[str, Any], key: str, value: Any) -> None:
    """Додає необов'язкове поле лише якщо воно має значення (JSON без шуму з null/порожніх)."""
    if value is None or value == "" or value == [] or value == {}:
        return
    out[key] = value


def _answer(data: Mapping[str, Any]) -> dict[str, Any]:
    ans: dict[str, Any] = {}
    if data.get("answer_source", "computed") == "computed":
        _put(ans, "computed", data.get("answer"))
    _put(ans, "book", data.get("answer_book"))
    if data.get("answer_verified"):
        ans["verified"] = True
    if data.get("answer_mismatch"):
        ans["mismatch"] = True
    return ans


def _figure_ids(node: Node) -> list[str]:
    return [c.data["figure_id"] for c in node.children if c.kind == "figure" and c.data.get("figure_id")]


class _Exporter:
    def __init__(self) -> None:
        self.figures: dict[str, dict[str, Any]] = {}
        self.skipped: list[dict[str, Any]] = []

    def _skip(self, node: Node, parent: Node) -> None:
        self.skipped.append({"code": "export_skipped", "severity": "warning",
                             "message": f"{node.kind} всередині {parent.kind} не має місця в схемі — пропущено",
                             "source": _source(node.source), "node_path": f"{parent.kind}/{node.kind}",
                             "text": (node.text or node.title)[:120]})

    # ---------------------------------------------------------------- листки

    def figure(self, node: Node) -> None:
        fid = node.data.get("figure_id")
        if not fid or fid in self.figures or node.source is None:
            return
        fig = {"id": fid, "number": node.number, "path": node.data.get("path"), "source": _source(node.source)}
        _put(fig, "title", node.title)
        self.figures[fid] = fig

    def subexercise(self, node: Node) -> dict[str, Any]:
        d = node.data
        out: dict[str, Any] = {"number": node.number or "", "text": node.text}
        if d.get("raw_label") and d.get("raw_label") != node.number:
            out["raw_label"] = d["raw_label"]
        if d.get("ocr_fixed"):
            out["label_fixed"] = True
        _put(out, "expr", d.get("expr"))
        _put(out, "expr_status", d.get("expr_status"))
        _put(out, "expr_issues", list(d.get("expr_issues", [])))
        _put(out, "answer", _answer(d))
        _put(out, "text_source", d.get("text_source"))
        _put(out, "ocr_text", d.get("ocr_text") if d.get("text_source") == "vision" else None)
        out["needs_review"] = node.needs_review
        return out

    def exercise(self, node: Node) -> dict[str, Any]:
        d = node.data
        for child in node.children:
            if child.kind == "figure":
                self.figure(child)
        out: dict[str, Any] = {
            "number": node.number or "",
            "difficulty": d.get("difficulty"),
            "condition": d.get("condition") or node.text,
            "subexercises": [self.subexercise(c) for c in node.children if c.kind == "subexercise"],
            "needs_review": node.needs_review,
            "source": _source(node.source),
        }
        _put(out, "difficulty_ocr", d.get("difficulty_ocr"))
        if "homework" in d:
            out["homework"] = bool(d["homework"])
        _put(out, "condition_tail", d.get("condition_tail"))
        for key in ("task_verb", "answer_kind"):
            _put(out, key, d.get(key))
        for key in ("is_word_problem", "auto_checkable", "has_fractions"):
            if key in d:
                out[key] = bool(d[key])
        answer = _answer(d)
        _put(out, "answer", answer)
        _put(out, "book_answer_parts", dict(d.get("answer_book_parts", {})))
        _put(out, "figure_ids", _figure_ids(node))
        _put(out, "figure_refs", [str(r) for r in d.get("figure_refs", [])])
        _put(out, "missing_figures", [str(r) for r in d.get("missing_figures", [])])
        _put(out, "text_source", d.get("text_source"))
        if d.get("text_source") == "vision" or d.get("vision_status"):
            _put(out, "ocr_text", d.get("ocr_text"))
            _put(out, "vision_text", d.get("vision_text"))
            _put(out, "vision_status", d.get("vision_status"))
            _put(out, "vision_reason", d.get("vision_reason"))
        _put(out, "flags", [f for f in EXERCISE_FLAGS if d.get(f)])
        return out

    # ---------------------------------------------------------------- контейнери

    def block(self, node: Node) -> dict[str, Any]:
        exercises = []
        for child in node.children:
            if child.kind == "exercise":
                exercises.append(self.exercise(child))
            elif child.kind == "figure":
                self.figure(child)
            else:
                self._skip(child, node)
        out: dict[str, Any] = {"type": node.data.get("block_type", "theory"), "text": node.text,
                               "exercises": exercises, "figure_ids": _figure_ids(node),
                               "needs_review": node.needs_review}
        _put(out, "title", node.title)
        out["source"] = _source(node.source)
        return out

    def _lesson_children(self, node: Node, allow_items: bool) -> tuple[list, list]:
        items, blocks = [], []
        for child in node.children:
            if child.kind == "block":
                blocks.append(self.block(child))
            elif child.kind == "item" and allow_items:
                items.append(self.item(child))
            elif child.kind == "figure":
                self.figure(child)
            else:
                self._skip(child, node)
        return items, blocks

    def item(self, node: Node) -> dict[str, Any]:
        _, blocks = self._lesson_children(node, allow_items=False)
        out = {"number": node.number or "", "title": node.title, "blocks": blocks}
        _put(out, "ocr_title", node.data.get("ocr_title"))
        _put(out, "figure_ids", _figure_ids(node))
        out["source"] = _source(node.source)
        return out

    def paragraph(self, node: Node) -> dict[str, Any]:
        items, blocks = self._lesson_children(node, allow_items=True)
        out = {"number": node.number or "", "title": node.title, "items": items, "blocks": blocks}
        _put(out, "ocr_title", node.data.get("ocr_title"))
        _put(out, "figure_ids", _figure_ids(node))
        out["source"] = _source(node.source)
        return out

    def section(self, node: Node) -> dict[str, Any]:
        paragraphs = []
        for child in node.children:
            if child.kind == "paragraph":
                paragraphs.append(self.paragraph(child))
            else:
                self._skip(child, node)
        return {"number": node.number or "", "title": node.title, "index": node.data.get("index"),
                "paragraphs": paragraphs, "source": _source(node.source)}


def _problem(problem: Any) -> dict[str, Any]:
    """Problem з validate.py (або вже dict) → формат схеми (джерело без службових line_ids)."""
    if isinstance(problem, Mapping):
        out = dict(problem)
        src = out.get("source")
        out["source"] = ({k: src.get(k) for k in ("pdf_page", "book_page", "bbox")} if src else None)
    else:
        out = {"code": problem.code, "severity": problem.severity, "message": problem.message,
               "source": _source(problem.source), "node_path": problem.node_path, "text": problem.text,
               "data": dict(problem.data)}
    if not out.get("data"):
        out.pop("data", None)
    return out


def _stats(sections: list[dict[str, Any]], figures: int) -> dict[str, int]:
    counts = {"sections": len(sections), "paragraphs": 0, "items": 0, "blocks": 0, "exercises": 0,
              "subexercises": 0, "figures": figures, "computed_answers": 0, "book_answers": 0,
              "verified_answers": 0, "needs_review": 0}

    def block(b: dict[str, Any]) -> None:
        counts["blocks"] += 1
        for ex in b["exercises"]:
            counts["exercises"] += 1
            counts["needs_review"] += ex["needs_review"]
            counts["book_answers"] += "book" in ex.get("answer", {}) or bool(ex.get("book_answer_parts"))
            for sub in ex["subexercises"]:
                counts["subexercises"] += 1
                ans = sub.get("answer", {})
                counts["computed_answers"] += "computed" in ans
                counts["book_answers"] += "book" in ans
                counts["verified_answers"] += bool(ans.get("verified"))

    for sec in sections:
        for par in sec["paragraphs"]:
            counts["paragraphs"] += 1
            for b in par["blocks"]:
                block(b)
            for it in par["items"]:
                counts["items"] += 1
                for b in it["blocks"]:
                    block(b)
    return counts


def export_textbook(root: Node, problems: Iterable[Any] = (), *, pdf_name: str, pdf_sha256: str,
                    created_at: str | None = None, pages: Iterable[int] = ()) -> dict[str, Any]:
    """Дерево + проблеми валідації → dict за схемою (перевіряється тут же)."""
    exporter = _Exporter()
    sections = []
    for child in root.children:
        if child.kind == "section":
            sections.append(exporter.section(child))
        else:
            exporter._skip(child, root)
    meta: dict[str, Any] = {
        "profile": root.data.get("profile", ""), "subject": root.data.get("subject", ""),
        "grade": int(root.data.get("grade", 0)), "title": root.title,
        "pdf_name": pdf_name, "pdf_sha256": pdf_sha256,
        "created_at": created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    _put(meta, "pages", sorted(set(pages)))
    problem_dicts = [_problem(p) for p in problems] + exporter.skipped
    figures = sorted(exporter.figures.values(), key=lambda f: (f["source"]["pdf_page"], f["id"]))
    data = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": __version__,
        "meta": meta,
        "stats": _stats(sections, len(figures)),
        "sections": sections,
        "figures": figures,
        "problems": problem_dicts,
    }
    validate_textbook(data)
    return data


def dumps(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def write_textbook(data: Mapping[str, Any], out_dir: str | Path = "pipeline_out") -> Path:
    """Пише ``<out_dir>/<profile>/textbook.json`` атомарно (після перевірки схемою)."""
    validate_textbook(data)
    path = Path(out_dir) / data["meta"]["profile"] / "textbook.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(dumps(data), encoding="utf-8")
    tmp.replace(path)
    return path


def load_textbook(path: str | Path) -> dict[str, Any]:
    """Читає експорт; інша ``schema_version`` → SchemaError з поясненням (не тихе «щось не те»)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    version = data.get("schema_version") if isinstance(data, dict) else None
    if version != SCHEMA_VERSION:
        raise SchemaError(f"{path}: schema_version={version!r}, а цей код розуміє {SCHEMA_VERSION}. "
                          "Перезапусти пайплайн або онови імпортер.")
    validate_textbook(data)
    return data
