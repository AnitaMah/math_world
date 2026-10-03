"""
Page numbers for grade 6 (Тарасенкова) straight from the book's own Зміст
(review/tarasenkova_toc_back/page-302.png, page-303.png) -- read directly
as images, not OCR'd. Tesseract badly mangles this page: the dotted
leaders between a title and its page number confuse its word
segmentation, and it glues digits from the section number onto the page
number (confirmed on multiple --psm attempts).

Why this exists: `data/grade_sources.py` already knows grade 6 is
"sections_only_no_items" -- Тарасенкова's own Зміст only lists Розділ/§,
no per-lesson item titles (Step 35's finding). Step 36 (deferred) is
extracting those item titles from each §'s actual pages -- but with no
page numbers, that meant rendering and OCR'ing some unknown subset of
all 305 pages just to find where a given § starts. This table removes
that guesswork: render the page(s) at and after each §'s start_page
below, rather than the whole book, when Step 36 is picked up.

CONFIDENCE NOTE -- read this before trusting any number below: this
book's Зміст uses a decorative serif font where "3" and "8" are drawn
almost identically at normal reading size. Two entries were caught and
corrected only by cross-checking that page numbers must strictly
increase down the list (a wrong digit reads locally plausible but breaks
that ordering against its neighbors):
  - § 18 "Циліндр. Конус. Куля" first read as page 180, which is *larger*
    than § 19 right after it (136) -- impossible. A tight crop still
    looked like "180" to the eye; corrected to 130 by ordering
    (123 < 130 < 136), not by a clearer image.
  - Розділ 5 and § 30 first read as 284/285, larger than § 31 right
    after (241) -- impossible. A tight crop confirmed 234/235 on
    re-inspection.
Every number below now forms one strictly increasing sequence from 4 to
300 with no other contradictions found, which is reassuring but not
proof -- an error that also happens to preserve ordering (e.g. swapping
two entries a similar distance apart) would not be caught this way.
Worth a quick visual spot-check against the real page before trusting
any single start_page for something that writes to the DB.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParagraphPage:
    section_number: int  # Розділ
    paragraph_number: int  # §
    title: str
    start_page: int  # 1-indexed *printed* page number (see PRINTED_TO_PDF_PAGE_OFFSET)


SECTION_START_PAGES = {
    1: 4,  # Розділ 1. Подільність натуральних чисел
    2: 30,  # Розділ 2. Звичайні дроби та дії з ними
    3: 86,  # Розділ 3. Відношення і пропорції
    4: 156,  # Розділ 4. Раціональні числа та дії з ними
    5: 234,  # Розділ 5. Вирази і рівняння
}

# Where the back matter actually landed, cross-referenced against this
# PDF's real page index (review/tarasenkova_toc_back/page-NNN.png):
# printed page 287 ("Відповіді") is at PDF page 296, so printed page
# numbers run about 9 pages behind this PDF's own page index (unnumbered
# front matter/cover pages). NOT yet confirmed against the front of the
# book (only checked at the back) -- verify before relying on it to
# render a specific §'s start page.
PRINTED_TO_PDF_PAGE_OFFSET = 9

PARAGRAPH_PAGES = [
    ParagraphPage(1, 1, "Дільники і кратні натурального числа. Прості числа", 5),
    ParagraphPage(1, 2, "Ознаки подільності на 2, 10, 5", 9),
    ParagraphPage(1, 3, "Ознаки подільності на 9, 3", 15),
    ParagraphPage(1, 4, "Розкладання чисел на множники. Найбільший спільний дільник", 20),
    ParagraphPage(1, 5, "Найменше спільне кратне", 26),
    ParagraphPage(2, 6, "Основна властивість дробу. Скорочення дробу", 31),
    ParagraphPage(2, 7, "Зведення дробів до спільного знаменника. Порівняння дробів", 39),
    ParagraphPage(2, 8, "Додавання і віднімання дробів", 47),
    ParagraphPage(2, 9, "Множення дробів. Знаходження дробу від числа", 55),
    ParagraphPage(2, 10, "Ділення дробів. Знаходження числа за його дробом", 67),
    ParagraphPage(2, 11, "Перетворення звичайного дробу в десятковий. Десяткові наближення звичайного дробу", 77),
    ParagraphPage(3, 12, "Відношення та його властивості", 87),
    ParagraphPage(3, 13, "Пропорція та її властивості", 93),
    ParagraphPage(3, 14, "Пряма та обернена пропорційні залежності", 101),
    ParagraphPage(3, 15, "Поділ числа в даному відношенні. Масштаб", 109),
    ParagraphPage(3, 16, "Коло і круг. Круговий сектор", 116),
    ParagraphPage(3, 17, "Діаграми", 123),
    ParagraphPage(3, 18, "Циліндр. Конус. Куля", 130),  # corrected from a misread 180 -- see CONFIDENCE NOTE
    ParagraphPage(3, 19, "Відсоткові розрахунки", 136),
    ParagraphPage(3, 20, "Ймовірність випадкової події", 147),
    ParagraphPage(4, 21, "Додатні та від'ємні числа. Число нуль", 157),
    ParagraphPage(4, 22, "Координатна пряма", 163),
    ParagraphPage(4, 23, "Модуль числа", 170),
    ParagraphPage(4, 24, "Цілі числа. Раціональні числа", 180),
    ParagraphPage(4, 25, "Порівняння раціональних чисел", 186),
    ParagraphPage(4, 26, "Додавання раціональних чисел", 193),
    ParagraphPage(4, 27, "Віднімання раціональних чисел", 204),
    ParagraphPage(4, 28, "Множення раціональних чисел", 212),
    ParagraphPage(4, 29, "Ділення раціональних чисел", 223),
    ParagraphPage(5, 30, "Вирази та їх спрощення", 235),  # corrected from a misread 285 -- see CONFIDENCE NOTE
    ParagraphPage(5, 31, "Рівняння. Основні властивості рівнянь", 241),
    ParagraphPage(5, 32, "Застосування рівнянь до розв'язування задач", 248),
    ParagraphPage(5, 33, "Перпендикулярні та паралельні прямі", 255),
    ParagraphPage(5, 34, "Координатна площина", 262),
    ParagraphPage(5, 35, "Графіки залежностей між величинами", 271),
]


def get_paragraph_page(paragraph_number: int) -> ParagraphPage:
    for p in PARAGRAPH_PAGES:
        if p.paragraph_number == paragraph_number:
            return p
    raise KeyError(f"No page entry for § {paragraph_number}")
