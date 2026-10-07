"""Етап 7: вправи детально — умова, підпункти, рисунки, тип задачі, домашнє завдання.

Структурний парсер (structure.py) уже знайшов кожну вправу і запам'ятав її рядки
(``data["line_keys"]``). Тут ми повертаємося до цих рядків (з координатами!) і:

* ділимо вправу на **умову** і **підпункти** ``1) 2) 3)`` — сітки читаються по
  колонках (grids.py), підпункти в рядку тексту («монетами: 1) по 5 к.; 2) …») теж;
* знаходимо посилання на рисунки «(рис. 15)»;
* визначаємо тип задачі для гри (обчислити / порівняти / побудувати / так-ні …);
* позначаємо домашнє завдання: кольоровий номер (Мерзляк) або іконка на полі (Тарасенкова).
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .datatypes import BBox, Line, Node, SourceRef
from .grids import Cell, find_grids, split_cells
from .layout import PageLayout
from .profiles import TextbookProfile

# «(рис. 15)», «на рисунку 15», «мал. 3», «на малюнку 3»; OCR: «puc.»
_FIGURE_REF_RE = re.compile(r"(?:рис(?:ун\w*)?|мал(?:юн\w*)?|puc)\.?\s*(\d+)", re.IGNORECASE)

# Дієслово-завдання → тип задачі. Порядок важливий: перше знайдене перемагає.
TASK_VERBS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("construction", ("накресліть", "побудуйте", "зобразіть", "позначте на", "перемалюйте", "виміряйте")),
    ("equation", ("розв'яжіть рівняння", "розв'яжіть рівняння:")),
    ("compute", ("обчисліть", "виконайте дії", "знайдіть значення", "виконайте додавання", "виконайте віднімання",
                 "виконайте множення", "виконайте ділення", "додайте", "відніміть", "помножте", "поділіть")),
    ("compare", ("порівняйте",)),
    ("order", ("розташуйте",)),
    ("write", ("запишіть", "подайте")),
    ("name", ("назвіть", "прочитайте", "укажіть")),
    ("prove", ("доведіть", "поясніть", "обґрунтуйте")),
    ("find", ("знайдіть", "визначте", "скільки")),
)
YES_NO_START = ("чи ",)
WORD_PROBLEM_HINTS = ("кг", "км", "грн", "учн", "год", "хв", "м ", "см", "років", "день", "купив", "магазин",
                      "зібрав", "пройшов", "проїхав", "швидк")
ANSWER_KIND = {"compute": "number", "equation": "number", "find": "number", "compare": "comparison",
               "order": "sequence", "construction": "none", "prove": "text", "name": "text", "write": "text"}
GAME_CHECKABLE = {"number", "comparison", "yes_no"}


# --------------------------------------------------------------------------- підпункти


@dataclass
class SplitExercise:
    condition: str
    cells: list[Cell]
    tail: str                 # текст після підпунктів («Якщо так, то наведіть приклади.»)
    grid_needs_review: bool
    figure_labels: str = ""   # підписи з рисунка, що потрапили в рядки вправи («А N К е R»)


def is_figure_label_line(line: Line) -> bool:
    """Рядок з підписів рисунка: майже самі 1–2-символьні «слова» (А, В, С, К) і жодного справжнього слова."""
    words = [w.text.strip(".,;:") for w in line.words]
    words = [w for w in words if w]
    if not words:
        return False
    short = sum(1 for w in words if len(w) <= 2)
    longest_alpha = max((sum(ch.isalpha() for ch in w) for w in words), default=0)
    return short / len(words) >= 0.6 and longest_alpha < 4 and not any(w[:1].isdigit() and w.endswith(")") for w in words)


def split_exercise(lines: list[Line], first_line_rest: str | None = None) -> SplitExercise:
    """Ділить рядки вправи на умову, підпункти і «хвіст».

    first_line_rest — текст першого рядка без номера вправи (з парсера), бо в Line
    номер «12.» ще стоїть першим словом.
    """
    grids = find_grids(lines)
    grid_of_line = {idx: g for g in grids for idx in g.line_indices}
    condition: list[str] = []
    tail: list[str] = []
    cells: list[Cell] = []
    review = any(g.needs_review for g in grids)
    done_grids: set[int] = set()
    figure_labels: list[str] = []

    for i, line in enumerate(lines):
        if i > 0 and i not in grid_of_line and is_figure_label_line(line):
            figure_labels.append(line.text)
            continue
        grid = grid_of_line.get(i)
        if grid is not None:
            if id(grid) not in done_grids:
                cells.extend(grid.cells)
                done_grids.add(id(grid))
            continue
        text = first_line_rest if (i == 0 and first_line_rest is not None) else line.text
        if i == 0 and first_line_rest is not None:
            words = line.words[len(line.words) - len(first_line_rest.split()):] if first_line_rest else []
            prefix, inline = split_cells(Line(words=words, page_index=line.page_index), row=i)
        else:
            prefix, inline = split_cells(line, row=i)
        prefix_text = " ".join(w.text for w in prefix) if inline else text
        if inline:
            if prefix_text:
                (tail if cells else condition).append(prefix_text)
            for c in inline:
                c.label = c.raw_label
            cells.extend(inline)
        elif cells:
            # Рядок без маркерів після підпунктів: або продовження останнього підпункту
            # (перенос), або «хвіст» умови. Продовження — якщо попередній підпункт не закінчився «;» / «.» / «?».
            last = cells[-1]
            if last.words and not last.text.endswith((";", ".", "?", "!")):
                last.words.extend(line.words)
            else:
                tail.append(prefix_text)
        else:
            condition.append(prefix_text)
    return SplitExercise(" ".join(condition).strip(), cells, " ".join(tail).strip(), review,
                         " ".join(figure_labels))


# --------------------------------------------------------------------------- класифікація


def classify_task(condition: str, has_subitems: bool) -> dict[str, object]:
    """Тип задачі для гри за дієсловом умови (дуже грубо, але прозоро)."""
    text = condition.lower().replace("’", "'")
    task = "other"
    for name, verbs in TASK_VERBS:
        if any(v in text for v in verbs):
            task = name
            break
    if text.startswith(YES_NO_START) or (task == "other" and " чи " in text and text.rstrip().endswith("?")):
        answer = "yes_no"
    else:
        answer = ANSWER_KIND.get(task, "text")
    words = len(condition.split())
    word_problem = (not has_subitems and words >= 12 and condition.rstrip().endswith("?")
                    and any(h in text for h in WORD_PROBLEM_HINTS))
    return {
        "task_verb": task,
        "answer_kind": answer,
        "is_word_problem": word_problem,
        "auto_checkable": answer in GAME_CHECKABLE,
    }


def figure_refs(text: str) -> list[str]:
    return sorted(set(_FIGURE_REF_RE.findall(text)), key=int)


# --------------------------------------------------------------------------- домашнє завдання


def is_colored(image: np.ndarray, box: BBox, min_share: float = 0.3) -> bool:
    """Чи надруковано текст у прямокутнику кольором (зелений/синій номер), а не чорним.

    Беремо лише «чорнило» (темніші за фон пікселі) і дивимося, яка їх частка насичена.
    """
    import cv2
    h, w = image.shape[:2]
    crop = image[max(box.y0, 0):min(box.y1, h), max(box.x0, 0):min(box.x1, w)]
    if crop.size == 0 or crop.ndim != 3:
        return False
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    ink = hsv[..., 2] < 200
    if ink.sum() < 5:
        return False
    saturated = (hsv[..., 1] > 80) & ink
    return saturated.sum() / ink.sum() >= min_share


def has_margin_icon(image: np.ndarray, box: BBox, width: int = 60, min_ink: float = 0.08) -> bool:
    """Чи є іконка (будиночок) на полі зліва від номера вправи."""
    import cv2
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    x1 = max(box.x0 - 5, 0)
    x0 = max(x1 - width, 0)
    y0, y1 = max(box.y0 - 10, 0), min(box.y1 + 25, h)
    region = gray[y0:y1, x0:x1]
    if region.size == 0:
        return False
    return float((region < 160).mean()) >= min_ink


def detect_difficulty_mark(image: np.ndarray, number_box: BBox, next_box: BBox | None = None) -> str | None:
    """Значок складності за **картинкою**: ◦ (кружечок), • (крапка), •• (дві), * (зірочка) або None.

    OCR часто губить ці дрібні надрядкові значки (◦ зникає, • стає «"»). Тому
    дивимося на пікселі: беремо смугу над серединою номера вправи, від початку номера
    до наступного слова, і шукаємо маленькі окремі плями, що не торкаються країв
    смуги (цифри номера торкаються нижнього краю — їх відкидаємо).
    Кружечок має «дірку» (вкладений контур), зірочка — «рвана» (мала опуклість).
    """
    import cv2
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h = max(number_box.height, 1)
    y0 = max(number_box.y0 - int(0.6 * h), 0)
    y1 = number_box.y0 + int(0.55 * h)
    x0 = number_box.x0
    x1 = next_box.x0 if next_box is not None and next_box.x0 > x0 else number_box.x1 + h
    crop = gray[y0:y1, x0:x1]
    if crop.size == 0 or (crop < 150).sum() == 0:
        return None
    _, ink = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, hierarchy = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return None
    ch, cw = crop.shape
    dots = rings = stars = 0
    for i, contour in enumerate(contours):
        if hierarchy[0][i][3] != -1:                  # внутрішній контур (дірка) — не окрема пляма
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        if y == 0 or y + bh >= ch - 1:                # торкається краю: цифра номера або рядок вище
            continue
        if bw * bh < 6 or bw > 0.6 * h or bh > 0.6 * h:
            continue
        has_hole = hierarchy[0][i][2] != -1
        area = cv2.contourArea(contour)
        hull = cv2.contourArea(cv2.convexHull(contour)) or 1.0
        if has_hole:
            rings += 1
        elif area / hull < 0.6 and bw >= 5:
            stars += 1
        else:
            dots += 1
    if rings:
        return "◦"
    if stars:
        return "*"
    if dots >= 2:
        return "••"
    if dots == 1:
        return "•"
    return None


# --------------------------------------------------------------------------- головна функція


@dataclass
class EnrichStats:
    exercises: int = 0
    with_subitems: int = 0
    subitems: int = 0
    homework: int = 0
    auto_checkable: int = 0
    missing_lines: int = 0
    difficulty_from_image: int = 0     # скільки разів значок з картинки змінив рівень з OCR
    difficulty_suspicious: int = 0     # складність «спадає» в блоці — перевірити


def enrich_exercises(
    root: Node,
    layouts: Iterable[PageLayout],
    profile: TextbookProfile,
    page_images: Mapping[int, Path] | None = None,
) -> EnrichStats:
    """Доповнює кожну вправу дерева підпунктами й мітками (змінює дерево на місці)."""
    by_key: dict[tuple[int, int], Line] = {}
    for layout in layouts:
        for line in layout.body_lines:
            by_key[(layout.pdf_page, line.line_id)] = line
    images: dict[int, np.ndarray] = {}

    def image_for(page: int) -> np.ndarray | None:
        if not page_images or page not in page_images:
            return None
        if page not in images:
            from .preprocess import load_image
            images[page] = load_image(page_images[page])
        return images[page]

    stats = EnrichStats()
    parent_block_type = {id(ex): block.data.get("block_type")
                         for block in root.find("block") for ex in block.children if ex.kind == "exercise"}
    for ex in root.find("exercise"):
        stats.exercises += 1
        keys = [tuple(k) for k in ex.data.get("line_keys", [])]
        lines = [by_key[k] for k in keys if k in by_key]
        if len(lines) != len(keys):
            stats.missing_lines += 1
        if not lines:
            continue
        first_rest = ex.text.splitlines()[0] if ex.text else ""
        split = split_exercise(lines, first_rest)
        ex.data["condition"] = split.condition
        if split.tail:
            ex.data["condition_tail"] = split.tail
        if split.figure_labels:
            ex.data["figure_labels"] = split.figure_labels
        ex.children = [c for c in ex.children if c.kind != "subexercise"]
        for cell in split.cells:
            if not cell.text:
                continue
            page = keys[0][0]
            ex.add(Node("subexercise", number=cell.label or cell.raw_label, text=cell.text,
                        source=SourceRef(pdf_page=page, bbox=cell.bbox) if cell.bbox else None,
                        needs_review=cell.ocr_fixed,
                        data={"raw_label": cell.raw_label, "ocr_fixed": cell.ocr_fixed}))
        if split.grid_needs_review:
            ex.needs_review = True
        subs = [c for c in ex.children if c.kind == "subexercise"]
        if subs:
            stats.with_subitems += 1
            stats.subitems += len(subs)

        ex.data.update(classify_task(split.condition, bool(subs)))
        refs = figure_refs(ex.text)
        if refs:
            ex.data["figure_refs"] = refs
        if ex.data.get("auto_checkable"):
            stats.auto_checkable += 1

        # Домашнє завдання і значок складності — за першим словом (номером) першого рядка.
        first = lines[0]
        img = image_for(keys[0][0])
        homework = False
        is_oral = parent_block_type.get(id(ex)) == "oral_exercise"
        if img is not None and first.words:
            number_box = first.words[0].bbox
            next_box = first.words[1].bbox if len(first.words) > 1 else None
            if not is_oral:     # усні вправи не бувають домашніми (а їхні номери теж кольорові)
                if profile.homework_marker == "colored_number":
                    homework = is_colored(img, number_box)
                elif profile.homework_marker == "margin_icon":
                    homework = has_margin_icon(img, number_box)
                if profile.difficulty_from_image:
                    symbol = detect_difficulty_mark(img, number_box, next_box)
                    level = profile.difficulty_marks.get(symbol) if symbol else None
                    ocr_level = ex.data.get("difficulty")
                    ex.data["difficulty_ocr"] = ocr_level
                    if level != ocr_level:
                        stats.difficulty_from_image += 1
                    ex.data["difficulty"] = level
                    if level and ex.needs_review and not ex.data.get("number_fixed"):
                        ex.needs_review = False     # «unknown» з OCR, а картинка дала відповідь
        ex.data["homework"] = bool(homework)
        stats.homework += bool(homework)

    if profile.difficulty_from_image:
        stats.difficulty_suspicious = flag_difficulty_order(root)
    return stats


LEVEL_RANK = {"preparatory": 0, "medium": 1, "sufficient": 2, "high": 3, "olympiad": 4}


def flag_difficulty_order(root: Node) -> int:
    """У блоці вправ складність не спадає (◦ … • … •• … *). Вправа, складніша за
    наступну, — підозріла: найчастіше картинка/OCR помилилися зі значком.
    Позначаємо needs_review і повертаємо кількість таких вправ."""
    flagged = 0
    for block in root.find("block"):
        exercises = [e for e in block.children if e.kind == "exercise"]
        for cur, nxt in zip(exercises, exercises[1:]):
            a, b = LEVEL_RANK.get(cur.data.get("difficulty")), LEVEL_RANK.get(nxt.data.get("difficulty"))
            if a is not None and b is not None and a > b:
                cur.needs_review = True
                cur.data["difficulty_suspicious"] = True
                flagged += 1
    return flagged
