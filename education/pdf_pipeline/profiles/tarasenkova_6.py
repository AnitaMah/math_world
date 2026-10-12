"""Тарасенкова, Богатирьова та ін. — «Математика, 6 клас».

Джерело правил — стор. 3 («Дорогі учні!»: рівні складності) і перевірені
сторінки 4–14. Структура: Розділ → § (урок). Пунктів усередині § немає.
Друкований номер сторінки = номер сторінки PDF по всій книзі (стор. 13 = 13,
колонтитул на PDF 296 показує 296). Відповіді — PDF 287–299, далі покажчик і зміст.
"""
import re

from .base import BlockMarker, TextbookProfile

PROFILE = TextbookProfile(
    code="math_tarasenkova_6",
    subject_code="math",
    grade=6,
    author="Тарасенкова Н. А., Богатирьова І. М., Коломієць О. М., Сердюк З. О.",
    year=2014,
    title="Математика. 6 клас",
    pdf_name="Matematyka_6klas_Tarasenkova.pdf",
    lesson_level="paragraph",
    section_re=re.compile(r"^Розділ\s+(?P<num>\d+)\.?\s*(?P<title>.*)$", re.IGNORECASE),
    # «§ 2. ОЗНАКИ ПОДІЛЬНОСТІ НА 2, 10, 5» — назва великими літерами.
    paragraph_re=re.compile(r"^§\s*(?P<num>\d{1,2})\.\s*(?P<title>.+)$"),
    item_re=None,
    # «35′. Назвіть…», «40°. Із чисел…», «63. Перемалюйте…», «72*. Запишіть…» — значок ПЕРЕД крапкою.
    exercise_re=re.compile(r"^(?P<num>\d{1,8})\s*(?P<mark>[′'’`°o*\"”])?\s*[.,]\s*(?P<rest>.*)$"),
    block_markers=(
        BlockMarker("worked_example", ("Задача",), whole_line=False),      # «Задача. Знайдіть…» + «Розв'язання.»
        BlockMarker("rule", ("Запам'ятайте",)),
        BlockMarker("note", ("Зверніть увагу",)),
        BlockMarker("extra_reading", ("Дізнайтеся більше",)),
        BlockMarker("self_check", ("Пригадайте головне",), threshold=80, partial=True),
        BlockMarker("exercise", ("Розв'яжіть задачі",), threshold=80, partial=True),
        BlockMarker("applied_exercise", ("Застосуйте на практиці",), threshold=80, partial=True),
        BlockMarker("review_exercise", ("Задачі на повторення",), threshold=80, partial=True),
    ),
    difficulty_marks={
        "′": "preparatory", "'": "preparatory", "’": "preparatory", "`": "preparatory",  # штрих
        "°": "medium", "o": "medium", '"': "medium", "”": "medium",                                                  # кружечок
        "*": "high",                                                                    # зірочка
    },
    default_difficulty="sufficient",     # без значка — достатній рівень
    homework_marker="margin_icon",       # будиночок на полі зліва від номера
    toc_path="data/6_class_ukr.txt",
    strict_figures=True,
    book_page_offset=0,                  # стор. друкована = стор. PDF
    skip_pages=frozenset({1, 2, 3, *range(300, 306)}),   # 300–301 покажчик, 302–305 зміст
    answers_pages=(287, 299),
    notes=(
        "«?» на полі — питання в теорії, лишається частиною теорії.",
        "«Задача.» відкриває розв'язаний приклад; «Розв'язання.» / «Спосіб 1.» — його частини.",
        "92 сторінки мають ~76 ppi (пресет lowres).",
        "Дроби в «Задачі на повторення» двоповерхові — OCR їх не прочитає (фаза 11).",
    ),
)
