"""Спільні типи даних пайплайна: від слова з OCR до дерева підручника.

Усі класи серіалізуються в JSON-сумісні dict (``to_dict``) і назад
(``from_dict``) без втрат — так проміжні результати кешуються на диску.
Координати завжди в пікселях **оригінальної** картинки сторінки.
"""
from __future__ import annotations

import statistics
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- BBox


@dataclass(frozen=True)
class BBox:
    """Прямокутник на сторінці: лівий-верхній (x0, y0) і правий-нижній (x1, y1) кут."""

    x0: int
    y0: int
    x1: int
    y1: int

    def __post_init__(self) -> None:
        if self.x0 > self.x1 or self.y0 > self.y1:
            raise ValueError(f"Некоректний BBox: {self}")

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def union(self, other: BBox) -> BBox:
        """Найменший прямокутник, що містить обидва."""
        return BBox(min(self.x0, other.x0), min(self.y0, other.y0),
                    max(self.x1, other.x1), max(self.y1, other.y1))

    def intersection(self, other: BBox) -> BBox | None:
        """Спільна частина двох прямокутників або None, якщо вони не перетинаються."""
        x0, y0 = max(self.x0, other.x0), max(self.y0, other.y0)
        x1, y1 = min(self.x1, other.x1), min(self.y1, other.y1)
        if x0 >= x1 or y0 >= y1:
            return None
        return BBox(x0, y0, x1, y1)

    def intersects(self, other: BBox) -> bool:
        return self.intersection(other) is not None

    def iou(self, other: BBox) -> float:
        """Intersection over Union: 0 — не перетинаються, 1 — однакові."""
        inter = self.intersection(other)
        if inter is None:
            return 0.0
        union_area = self.area + other.area - inter.area
        return inter.area / union_area if union_area else 0.0

    def scale(self, factor: float) -> BBox:
        """Масштабує координати (напр. з апскейленої картинки назад в оригінал: factor=0.5)."""
        return BBox(round(self.x0 * factor), round(self.y0 * factor),
                    round(self.x1 * factor), round(self.y1 * factor))

    def shift(self, dx: int, dy: int) -> BBox:
        """Зсуває прямокутник (напр. після обрізки полів)."""
        return BBox(self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy)

    @staticmethod
    def union_all(boxes: Iterable[BBox]) -> BBox:
        """Об'єднання кількох прямокутників. Порожній список — помилка."""
        boxes = list(boxes)
        if not boxes:
            raise ValueError("union_all: порожній список")
        result = boxes[0]
        for box in boxes[1:]:
            result = result.union(box)
        return result

    def to_dict(self) -> list[int]:
        # Компактно: [x0, y0, x1, y1] — таких об'єктів у JSON будуть тисячі.
        return [self.x0, self.y0, self.x1, self.y1]

    @classmethod
    def from_dict(cls, data: list[int]) -> BBox:
        x0, y0, x1, y1 = data
        return cls(int(x0), int(y0), int(x1), int(y1))


# --------------------------------------------------------------------------- Word


@dataclass(frozen=True)
class Word:
    """Одне слово, як його повернув OCR."""

    text: str
    bbox: BBox
    conf: float                 # впевненість OCR, 0..100
    block_no: int = 0           # номери з Tesseract: блок / абзац / рядок / слово
    par_no: int = 0
    line_no: int = 0
    word_no: int = 0
    raw_text: str | None = None  # текст до нормалізації (фаза 7); None — не змінювався
    flags: tuple[str, ...] = ()  # позначки для перевірки, напр. "suspect_operator"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "bbox": self.bbox.to_dict(),
            "conf": self.conf,
            "block_no": self.block_no,
            "par_no": self.par_no,
            "line_no": self.line_no,
            "word_no": self.word_no,
            "raw_text": self.raw_text,
            "flags": list(self.flags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Word:
        return cls(
            text=data["text"],
            bbox=BBox.from_dict(data["bbox"]),
            conf=float(data["conf"]),
            block_no=data.get("block_no", 0),
            par_no=data.get("par_no", 0),
            line_no=data.get("line_no", 0),
            word_no=data.get("word_no", 0),
            raw_text=data.get("raw_text"),
            flags=tuple(data.get("flags", ())),
        )


# --------------------------------------------------------------------------- Line


@dataclass
class Line:
    """Рядок тексту на сторінці — впорядкований список слів."""

    words: list[Word]
    page_index: int             # номер сторінки в PDF (з 1)
    zone: str = "body"          # "header" | "footer" | "body" | "boxed" | ...
    line_id: int = 0            # порядковий номер рядка на сторінці

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def bbox(self) -> BBox:
        return BBox.union_all(w.bbox for w in self.words)

    @property
    def conf(self) -> float:
        """Середня впевненість слів; 0 для порожнього рядка."""
        return statistics.fmean(w.conf for w in self.words) if self.words else 0.0

    @property
    def min_conf(self) -> float:
        return min((w.conf for w in self.words), default=0.0)

    @property
    def height(self) -> float:
        """Медіанна висота слів — «розмір шрифту» рядка (заголовки вищі)."""
        return statistics.median(w.bbox.height for w in self.words) if self.words else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "words": [w.to_dict() for w in self.words],
            "page_index": self.page_index,
            "zone": self.zone,
            "line_id": self.line_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Line:
        return cls(
            words=[Word.from_dict(w) for w in data["words"]],
            page_index=data["page_index"],
            zone=data.get("zone", "body"),
            line_id=data.get("line_id", 0),
        )


# --------------------------------------------------------------------------- Zone


@dataclass
class Zone:
    """Область сторінки певного типу (колонтитул, рамка, рисунок...)."""

    kind: str
    bbox: BBox
    lines: list[Line] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "bbox": self.bbox.to_dict(),
                "lines": [ln.to_dict() for ln in self.lines]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Zone:
        return cls(kind=data["kind"], bbox=BBox.from_dict(data["bbox"]),
                   lines=[Line.from_dict(ln) for ln in data.get("lines", [])])


# --------------------------------------------------------------------------- PageImage


@dataclass(frozen=True)
class PageImage:
    """Картинка однієї сторінки PDF, збережена на диску."""

    pdf_page: int               # номер сторінки в PDF, з 1
    path: Path
    width: int
    height: int
    dpi: float
    low_res: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"pdf_page": self.pdf_page, "path": self.path.as_posix(),
                "width": self.width, "height": self.height,
                "dpi": self.dpi, "low_res": self.low_res}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageImage:
        return cls(pdf_page=data["pdf_page"], path=Path(data["path"]),
                   width=data["width"], height=data["height"],
                   dpi=float(data["dpi"]), low_res=data.get("low_res", False))


# --------------------------------------------------------------------------- PageOcr


@dataclass
class PageOcr:
    """Результат OCR однієї сторінки."""

    page: PageImage
    words: list[Word]
    engine: str                 # напр. "tesseract-5.5.3"
    params: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"page": self.page.to_dict(), "words": [w.to_dict() for w in self.words],
                "engine": self.engine, "params": dict(self.params),
                "duration_ms": self.duration_ms}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageOcr:
        return cls(page=PageImage.from_dict(data["page"]),
                   words=[Word.from_dict(w) for w in data["words"]],
                   engine=data["engine"], params=dict(data.get("params", {})),
                   duration_ms=data.get("duration_ms", 0))


# --------------------------------------------------------------------------- SourceRef


@dataclass(frozen=True)
class SourceRef:
    """Звідки взявся шматок тексту: сторінка і місце на ній. Є в кожній ноді дерева."""

    pdf_page: int
    book_page: int | None = None     # номер, надрукований у книзі
    bbox: BBox | None = None
    line_ids: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"pdf_page": self.pdf_page, "book_page": self.book_page,
                "bbox": self.bbox.to_dict() if self.bbox else None,
                "line_ids": list(self.line_ids)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceRef:
        bbox = data.get("bbox")
        return cls(pdf_page=data["pdf_page"], book_page=data.get("book_page"),
                   bbox=BBox.from_dict(bbox) if bbox else None,
                   line_ids=tuple(data.get("line_ids", ())))


# --------------------------------------------------------------------------- Node

NODE_KINDS = frozenset({
    "textbook", "section", "paragraph", "item", "block",
    "exercise", "subexercise", "figure", "answer",
})


@dataclass
class Node:
    """Вузол дерева підручника: Розділ → § → пункт → блок → вправа → підпункт."""

    kind: str
    number: str | None = None        # "1", "11", "IV" — рядок, бо бувають римські
    title: str = ""
    text: str = ""
    children: list[Node] = field(default_factory=list)
    source: SourceRef | None = None
    conf: float | None = None
    needs_review: bool = False
    data: dict[str, Any] = field(default_factory=dict)  # додаткове: difficulty, block_type...

    def __post_init__(self) -> None:
        if self.kind not in NODE_KINDS:
            raise ValueError(f"Невідомий kind={self.kind!r}; дозволені: {sorted(NODE_KINDS)}")

    def add(self, child: Node) -> Node:
        """Додає дитину і повертає її (зручно: item = section.add(Node('item')))."""
        self.children.append(child)
        return child

    def walk(self) -> Iterator[Node]:
        """Обходить дерево в глибину: спочатку сам вузол, потім нащадки."""
        yield self
        for child in self.children:
            yield from child.walk()

    def find(self, kind: str) -> list[Node]:
        """Усі нащадки (і сам вузол) заданого типу, у порядку документа."""
        return [n for n in self.walk() if n.kind == kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "number": self.number,
            "title": self.title,
            "text": self.text,
            "children": [c.to_dict() for c in self.children],
            "source": self.source.to_dict() if self.source else None,
            "conf": self.conf,
            "needs_review": self.needs_review,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Node:
        source = data.get("source")
        return cls(
            kind=data["kind"],
            number=data.get("number"),
            title=data.get("title", ""),
            text=data.get("text", ""),
            children=[cls.from_dict(c) for c in data.get("children", [])],
            source=SourceRef.from_dict(source) if source else None,
            conf=data.get("conf"),
            needs_review=data.get("needs_review", False),
            data=dict(data.get("data", {})),
        )
