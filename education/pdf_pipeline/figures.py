"""Етап 9: рисунки — знайти на сторінці, вирізати в окремі картинки, прив'язати до вправ.

Рисунки в підручниках рідко мають рамку (відрізки, промені, точки — просто лінії
на білому). Тому шукаємо так:

1. все «чорнило» сторінки;
2. мінус справжній текст (рамки рядків OCR з нормальними словами);
3. що лишилося і злипається в помітні плями — це рисунки (разом з їхніми
   підписами-літерами A, B, C, бо такі «рядки» ми текстом не вважаємо);
4. підпис «Рис. 15» / «Мал. 3» під рисунком дає йому номер;
5. вправа з «(рис. 15)» отримує свій рисунок.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .datatypes import BBox, Line, Node, SourceRef
from .exercises import is_figure_label_line
from .layout import PageLayout

# «Рис. 15», «Puc. 4», «Мал. 1», «Рис. З» (З замість 3), «Рис. 27, б»
CAPTION_RE = re.compile(r"(?:Рис|Puc|Pис|Мал|Mал)\.?\s*([0-9ЗзОо]{1,3})", re.IGNORECASE)
_DIGIT_FIX = str.maketrans({"З": "3", "з": "3", "О": "0", "о": "0"})
MIN_FIGURE_SIDE = 2.0     # у висотах рядка
PAD = 6


@dataclass
class Figure:
    """Рисунок на сторінці."""

    pdf_page: int
    bbox: BBox
    number: str | None = None        # «15» з підпису «Рис. 15»
    path: Path | None = None
    from_frame: bool = False
    caption_bbox: BBox | None = None     # де надруковано «Рис. N» (щоб не вирізати його в картинку)

    @property
    def figure_id(self) -> str:
        suffix = f"ris{self.number}" if self.number else f"y{self.bbox.y0}"
        return f"p{self.pdf_page:03d}_{suffix}"

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.figure_id, "pdf_page": self.pdf_page, "bbox": self.bbox.to_dict(),
                "number": self.number, "path": self.path.as_posix() if self.path else None}


# --------------------------------------------------------------------------- підписи


def find_captions(lines: Iterable[Line]) -> list[tuple[str, BBox]]:
    """Підписи «Рис. N» у рядках: [(номер, bbox підпису)]. Один рядок може мати два підписи."""
    found: list[tuple[str, BBox]] = []
    for line in lines:
        words = line.words
        for i, word in enumerate(words):
            pair = word.text if i + 1 >= len(words) else f"{word.text} {words[i + 1].text}"
            m = CAPTION_RE.match(pair)
            if not m or not word.text[:1].isalpha():
                continue
            number = m.group(1).translate(_DIGIT_FIX)
            if not number.isdigit():
                continue
            box = word.bbox if i + 1 >= len(words) else word.bbox.union(words[i + 1].bbox)
            found.append((str(int(number)), box))
    return found


def is_caption_line(line: Line) -> bool:
    return bool(CAPTION_RE.match(line.text)) and len(line.words) <= 6


# --------------------------------------------------------------------------- пошук рисунків


def _is_real_text(line: Line) -> bool:
    """Рядок справжнього тексту (його маскуємо), а не підписи-літери рисунка."""
    if is_figure_label_line(line) or is_caption_line(line):
        return False
    has_content = any(sum(ch.isalnum() for ch in w.text) >= 2 for w in line.words)
    return has_content and line.conf >= 40


def _merge_boxes(boxes: list[BBox], gap: int) -> list[BBox]:
    """Об'єднує прямокутники, що перетинаються або ближчі за gap."""
    merged = list(boxes)
    changed = True
    while changed:
        changed = False
        out: list[BBox] = []
        for box in merged:
            grown = BBox(box.x0 - gap, box.y0 - gap, box.x1 + gap, box.y1 + gap)
            for i, other in enumerate(out):
                if grown.intersects(other):
                    out[i] = other.union(box)
                    changed = True
                    break
            else:
                out.append(box)
        merged = out
    return merged


def _split_side_by_side(box: BBox, boxes_src: list[BBox], caps: list[BBox], text_height: int) -> list[BBox]:
    """Розділяє злиту область, якщо під нею в одному ряду стоять ≥2 підписи «Рис. N» (рис. 22 і 23 поруч).

    Первинні плями розкладаємо за найближчим по горизонталі підписом; якщо кожен підпис
    отримав свої плями — повертаємо окремі області, інакше лишаємо як було.
    """
    row = [c for c in caps if box.x0 - text_height <= c.center[0] <= box.x1 + text_height
           and 0 <= c.y0 - box.y1 <= text_height * 6]
    if len(row) < 2 or len(boxes_src) < 2:
        return [box]
    groups: dict[int, list[BBox]] = {}
    for b in boxes_src:
        j = min(range(len(row)), key=lambda k: abs(row[k].center[0] - b.center[0]))
        groups.setdefault(j, []).append(b)
    if len(groups) < 2:
        return [box]
    return [BBox.union_all(g) for g in groups.values()]


def find_figure_regions(image: np.ndarray, layout: PageLayout, text_height: int | None = None) -> list[BBox]:
    """Області рисунків на сторінці (у пікселях оригінальної картинки)."""
    import cv2
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h_img, w_img = gray.shape
    if text_height is None:
        heights = [ln.height for ln in layout.body_lines if ln.words]
        text_height = int(np.median(heights)) if heights else max(round(h_img * 0.0135), 8)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Колонтитул і текст — геть.
    ink[: int(h_img * layout_header_band(layout)), :] = 0
    for line in [*layout.body_lines, *layout.header_lines, *layout.footer_lines]:
        if line.words and (line.zone != "body" or _is_real_text(line)):
            b = line.bbox
            ink[max(b.y0 - 2, 0):b.y1 + 2, max(b.x0 - 2, 0):b.x1 + 2] = 0
    for line in layout.body_lines:            # підписи «Рис. N» теж не частина рисунка
        if is_caption_line(line):
            b = line.bbox
            ink[max(b.y0 - 2, 0):b.y1 + 2, max(b.x0 - 2, 0):b.x1 + 2] = 0

    # Злипаємо штрихи одного рисунка в одну пляму.
    k = max(text_height // 2, 3)
    blob = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    contours, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_side = int(text_height * MIN_FIGURE_SIDE)
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        big = w >= min_side and h >= min_side
        # Відрізок з точками (рис. 27–30). Тонша за ~0.65 рядка смуга — це підкреслення заголовка.
        long_thin = w >= text_height * 4 and h >= text_height * 0.65
        if (big or long_thin) and (ink[y:y + h, x:x + w] > 0).sum() > text_height * 3:
            boxes.append(BBox(x, y, x + w, y + h))
    boxes += [r.bbox for r in layout.regions if r.kind == "figure"]
    raw_boxes = list(boxes)
    merged = _merge_boxes(boxes, gap=text_height)
    boxes = []
    caps = [ln.bbox for ln in layout.body_lines if is_caption_line(ln)]
    for box in merged:
        boxes += _split_side_by_side(box, boxes_src=[b for b in raw_boxes if box.x0 <= b.x0 and box.y0 <= b.y0 and b.x1 <= box.x1 and b.y1 <= box.y1], caps=caps,
                                     text_height=text_height)
    return sorted((b for b in boxes if b.width < w_img * 0.95), key=lambda b: (b.y0, b.x0))


def layout_header_band(layout: PageLayout) -> float:
    """Частка висоти сторінки, зайнята колонтитулом (за його рядками), щоб не брати декор."""
    if not layout.header_lines:
        return 0.08
    return min(max(ln.bbox.y1 for ln in layout.header_lines) / layout.page_height + 0.01, 0.15)


def group_by_captions(regions: Sequence[BBox], captions: Sequence[tuple[str, BBox]],
                      text_lines: Sequence[Line], text_height: int) -> list[tuple[BBox, str | None]]:
    """Збирає частини рисунка (а, б, в, г) під одним підписом «Рис. N».

    Для кожного підпису беремо всі області **над ним**, але нижче за останній
    рядок звичайного тексту над підписом (там починається рисунок). Якщо в одному
    ряду кілька підписів («Рис. 27   Рис. 28»), частини ділимо за найближчим підписом
    по горизонталі. Області без підпису лишаються окремими рисунками без номера.
    """
    remaining = list(range(len(regions)))
    result: list[tuple[BBox, str | None]] = []

    def text_between(r: BBox, cap: BBox) -> bool:
        """Чи є звичайний текст між областю і підписом (у тій самій колонці)? Тоді це не його рисунок."""
        for ln in text_lines:
            b = ln.bbox
            overlaps = b.x0 < r.x1 and b.x1 > r.x0
            if overlaps and b.y0 >= r.y1 - 2 and b.y1 <= cap.y0 + 2:
                return True
        return False

    for number, cap in sorted(captions, key=lambda c: (c[1].y0, c[1].x0)):
        same_row = [c for _, c in captions if abs(c.y0 - cap.y0) <= text_height]
        mine = []
        for i in remaining:
            r = regions[i]
            if r.y1 > cap.y1 + text_height or cap.y0 - r.y1 > text_height * 25 or text_between(r, cap):
                continue
            nearest = min(same_row, key=lambda c: abs(c.center[0] - r.center[0]))
            if nearest is cap:
                mine.append(i)
        if mine:
            result.append((BBox.union_all(regions[i] for i in mine), number))
            remaining = [i for i in remaining if i not in mine]
    result += [(regions[i], None) for i in remaining]
    return sorted(result, key=lambda pair: (pair[0].y0, pair[0].x0))


def _absorb_label_lines(box: BBox, lines: Sequence[Line], text_height: int) -> BBox:
    """Додає до рисунка рядки-підписи (A, B, C, «ер», «ром»), що стоять впритул над/під ним.

    OCR інколи склеює підписи точок у «слова» по 2–3 літери, тому такі рядки не завжди
    визнаються підписами рисунка і маскуються як текст. Беремо рядки, що перетинаються з
    рисунком, розширеним на ~1.3 рядка по вертикалі, і не містять жодного слова з 4+ літер.
    """
    reach = int(text_height * 1.3)
    zone = BBox(box.x0, max(box.y0 - reach, 0), box.x1, box.y1 + reach)
    for line in lines:
        if not line.words or not line.bbox.intersects(zone) or is_caption_line(line):
            continue
        if any(sum(ch.isalpha() for ch in w.text) >= 4 for w in line.words):
            continue
        # Лише слова над/під самим рисунком: рядок «A B C D   M K E F» тягнеться під двома рисунками.
        for word in line.words:
            if word.bbox.x1 >= box.x0 - text_height and word.bbox.x0 <= box.x1 + text_height:
                box = box.union(word.bbox)
    return box


def crop_figure(image: np.ndarray, box: BBox, pad: int = PAD, bottom_limit: int | None = None) -> np.ndarray:
    """Вирізає рисунок із запасом pad (літери-підписи A, B, C часто стоять на самому краю).

    bottom_limit — не заходити нижче (верх підпису «Рис. N»).
    """
    h, w = image.shape[:2]
    y1 = min(box.y1 + pad, h)
    if bottom_limit is not None:
        y1 = max(min(y1, bottom_limit), box.y1)
    return image[max(box.y0 - pad, 0):y1, max(box.x0 - pad, 0):min(box.x1 + pad, w)].copy()


def extract_page_figures(image: np.ndarray, layout: PageLayout, out_dir: Path | None = None,
                         overwrite: bool = True) -> list[Figure]:
    """Усі рисунки сторінки з номерами; якщо out_dir — вирізає і зберігає PNG.

    overwrite=False — наявний PNG не перезаписуємо (повторний прогін оркестратора: запис
    PNG був найдовшою частиною етапу structure)."""
    heights = [ln.height for ln in layout.body_lines if ln.words]
    text_height = int(np.median(heights)) if heights else 18
    regions = find_figure_regions(image, layout, text_height)
    captions = find_captions(layout.body_lines)
    text_lines = [ln for ln in layout.body_lines if _is_real_text(ln)]
    frames = [r.bbox for r in layout.regions if r.kind == "figure"]
    caption_box = {}
    for number, box in captions:
        caption_box.setdefault(number, box)
    figures = []
    for box, number in group_by_captions(regions, captions, text_lines, text_height):
        cap = caption_box.get(number) if number else None
        if box.height < 2 * text_height:
            # Тонкий рисунок (відрізок з точками): літери-підписи A, B, C — над і під лінією.
            grow = int(text_height * 1.6)
            bottom = min(box.y1 + grow, image.shape[0])
            if cap is not None and cap.y0 > box.y1:
                bottom = min(bottom, cap.y0 - 2)
            box = BBox(box.x0, max(box.y0 - grow, 0), box.x1, max(bottom, box.y1))
        box = _absorb_label_lines(box, layout.body_lines, text_height)
        figures.append(Figure(layout.pdf_page, box, number, from_frame=any(box.iou(f) > 0.5 for f in frames),
                              caption_bbox=cap))
    if out_dir is not None:
        from .preprocess import save_image
        pad = max(PAD, int(text_height * 0.9))
        for fig in figures:
            fig.path = Path(out_dir) / f"{fig.figure_id}.png"
            if not overwrite and fig.path.exists():
                continue
            limit = fig.caption_bbox.y0 - 2 if fig.caption_bbox and fig.caption_bbox.y0 > fig.bbox.y1 else None
            save_image(fig.path, crop_figure(image, fig.bbox, pad, limit))
    return figures


# --------------------------------------------------------------------------- прив'язка до дерева


def _figure_node(fig: Figure) -> Node:
    return Node("figure", number=fig.number, title=f"Рис. {fig.number}" if fig.number else "",
                source=SourceRef(pdf_page=fig.pdf_page, bbox=fig.bbox),
                data={"figure_id": fig.figure_id, "path": fig.path.as_posix() if fig.path else None})


def attach_figures(root: Node, figures: Sequence[Figure], page_window: int = 4) -> dict[str, int]:
    """Вправи з «(рис. N)» отримують вузол-рисунок; рисунки без посилань — до теорії уроку.

    Номери рисунків повторюються в різних розділах, тому шукаємо рисунок з тим самим
    номером на сторінці вправи або поруч (±page_window).
    """
    stats = {"linked": 0, "missing": 0, "theory": 0}
    used: set[str] = set()
    by_number: dict[str, list[Figure]] = {}
    for fig in figures:
        if fig.number:
            by_number.setdefault(fig.number, []).append(fig)

    for ex in root.find("exercise"):
        refs = ex.data.get("figure_refs") or []
        page = ex.source.pdf_page if ex.source else None
        ex.children = [c for c in ex.children if c.kind != "figure"]
        for ref in refs:
            candidates = [f for f in by_number.get(ref, []) if page is None or abs(f.pdf_page - page) <= page_window]
            if not candidates and ex.source and ex.source.bbox:
                # Підпис «Рис. N» OCR не прочитав → беремо рисунок без номера поруч із вправою.
                box = ex.source.bbox
                nearby = [f for f in figures if f.number is None and f.pdf_page == page
                          and f.figure_id not in used and f.bbox.y0 < box.y1 + 3 * box.height]
                if nearby:
                    fig = min(nearby, key=lambda f: abs(f.bbox.center[1] - box.center[1]))
                    fig.number = ref
                    candidates = [fig]
            if not candidates:
                stats["missing"] += 1
                ex.data.setdefault("missing_figures", []).append(ref)
                continue
            fig = min(candidates, key=lambda f: abs(f.pdf_page - (page or f.pdf_page)))
            ex.add(_figure_node(fig))
            used.add(fig.figure_id)
            stats["linked"] += 1

    # Решта рисунків — до блоку теорії уроку, що йде на цій сторінці (останній урок, що почався не пізніше).
    lessons = [n for n in root.walk() if n.kind in ("item", "paragraph") and n.source]
    for fig in figures:
        if fig.figure_id in used:
            continue
        owner = None
        for lesson in lessons:
            if lesson.source.pdf_page <= fig.pdf_page:
                owner = lesson
        if owner is None:
            continue
        theory = next((b for b in owner.children if b.kind == "block" and b.data.get("block_type") == "theory"), owner)
        if not any(c.kind == "figure" and c.data.get("figure_id") == fig.figure_id for c in theory.children):
            theory.add(_figure_node(fig))
            stats["theory"] += 1
    return stats


def extract_all_figures(layouts: Iterable[PageLayout], page_images: Mapping[int, Path],
                        out_dir: Path | None = None, overwrite: bool = True) -> list[Figure]:
    """Рисунки з усіх сторінок."""
    from .preprocess import load_image
    figures: list[Figure] = []
    for layout in layouts:
        path = page_images.get(layout.pdf_page)
        if path is None:
            continue
        figures += extract_page_figures(load_image(path), layout, out_dir, overwrite)
    return figures
