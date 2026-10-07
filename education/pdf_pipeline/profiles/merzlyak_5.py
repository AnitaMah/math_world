"""Мерзляк, Полонський, Якір — «Математика, 5 клас» (2018).

Джерело правил — сторінки 3–4 самої книги («Від авторів», «Умовні позначення»)
і перевірені сторінки 5–15. Структура: Розділ (римські) → § → пункт (урок).
"""
import re

from .base import BlockMarker, TextbookProfile

PROFILE = TextbookProfile(
    code="math_merzlyak_5",
    subject_code="math",
    grade=5,
    author="Мерзляк А. Г., Полонський В. Б., Якір М. С.",
    year=2018,
    title="Математика. 5 клас",
    pdf_name="5-klas-matematika-merzljak-2018-1-46.pdf",
    lesson_level="item",
    section_re=re.compile(r"^Розділ\s+(?P<num>[IVX]+)\.?\s*(?P<title>.*)$", re.IGNORECASE),
    paragraph_re=re.compile(r"^§\s*(?P<num>\d{1,2})\.\s*(?P<title>.+)$"),
    item_re=re.compile(r"^(?P<num>\d{1,2})\.\s+(?P<title>[А-ЯІЇЄҐ].+)$"),
    # «8.• Скільки…», «11.•• Деяке…», «12. Обчисліть:» — значок ПІСЛЯ крапки.
    # OCR: • → " або ·; ◦ → ° або o; •• → "" / ·· / .. ; також «82» замість «8.•» (не ловимо — needs_review).
    exercise_re=re.compile(r'^(?P<num>\d{1,4})\.\s*(?P<mark>••|··|\.\.|""|[◦°•·"*])?\s*(?P<rest>\S.*)$'),
    block_markers=(
        BlockMarker("oral_exercise", ("Розв'язуємо усно",)),
        BlockMarker("exercise", ("Вправи",), threshold=90),
        BlockMarker("review_exercise", ("Вправи для повторення",)),
        BlockMarker("wise_owl", ("Задача від Мудрої Сови",)),
        BlockMarker("history_aside", ("Коли зроблено уроки",)),
        # «Завдання № 1 «Перевірте себе» в тестовій формі» — номер змінюється, тому поріг нижчий.
        BlockMarker("self_test", ("Завдання 1 Перевірте себе в тестовій формі",), threshold=80),
        BlockMarker("summary", ("Головне в параграфі",), whole_line=False),
    ),
    difficulty_marks={
        "◦": "medium", "°": "medium",               # початковий і середній рівні
        "•": "sufficient", "·": "sufficient",       # достатній
        "••": "high", "··": "high", "..": "high",   # високий
        "*": "olympiad",                            # для гуртків і факультативів
        '"': "sufficient", '""': "high",            # як OCR читає • / •• (перевіряти!)
    },
    default_difficulty=None,             # без значка (вправи для повторення) — рівень не вказано
    homework_marker="colored_number",    # номер, надрукований кольором (зелений «10.•»)
    toc_path="data/5_class_ukr.txt",
    skip_pages=frozenset({1, 2, 3, 4}),  # обкладинка, титул, «Від авторів», «Умовні позначення»
    notes=(
        "Самоперевірка (1. Як називають…) іде після теорії без заголовка — розпізнається парсером за позицією.",
        "◀ — кінець розв'язування прикладу в теорії.",
        "Номер-колір (домашнє завдання) OCR не бачить — визначати за кольором пікселів (фаза 10).",
    ),
)
