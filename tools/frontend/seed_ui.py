"""Демо-дані для візуальних тестів (фаза 19): невелика база, з якою екрани виглядають стабільно.

Мапа й гра на знімках беруть дані з моків (`?mock=demo`, `?mock=1`); з бази — лише верхня панель
(класи), картки «Світу», сторінка уроку і вхід. Тому тут кілька записів, а не весь підручник.

    DB_PATH=/tmp/ui.sqlite3 python manage.py migrate
    DB_PATH=/tmp/ui.sqlite3 python tools/frontend/seed_ui.py

**Лише в окрему базу**: без DB_PATH (тобто в робочу db.sqlite3) скрипт відмовляється працювати.
Повторний запуск нічого не дублює. Друкує id уроку для `visual.spec.js` (він завжди 1 у новій базі).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "math_world.settings")

if not os.environ.get("DB_PATH"):
    sys.exit("seed_ui.py: задай DB_PATH=<окрема база>, щоб не змішати демо-дані з робочою db.sqlite3")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402

from education.models import (  # noqa: E402
    Answer, ContentBlock, Exercise, Grade, Item, Paragraph, Section, SubExercise, Subject, Textbook,
)

THEORY = """Якщо ви добре заточеним олівцем доторкнетеся до аркуша зошита,
то залишиться слід, який дає уявлення про точку.
Відмітимо на аркуші паперу дві точки A і B. Ці точки можна сполучити
всілякими лініями. Найкоротшу лінію можна провести за допомогою лінійки.
Отриману лінію називають відрізком, а точки A і B — кінцями відрізка."""


@transaction.atomic
def seed() -> Item:
    math, _ = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})
    g5, _ = Grade.objects.get_or_create(subject=math, number=5, defaults={"name_uk": "5 клас"})
    g6, _ = Grade.objects.get_or_create(subject=math, number=6, defaults={"name_uk": "6 клас"})
    tb5, _ = Textbook.objects.get_or_create(pdf_sha256="ui-demo-5".ljust(64, "0"), defaults=dict(
        subject=math, grade=g5, profile_code="math_merzlyak_5", title="Математика 5",
        author="Мерзляк А. Г., Полонський В. Б., Якір М. С.", year=2018))
    tb6, _ = Textbook.objects.get_or_create(pdf_sha256="ui-demo-6".ljust(64, "0"), defaults=dict(
        subject=math, grade=g6, profile_code="math_tarasenkova_6", title="Математика 6",
        author="Тарасенкова Н. А., Богатирьова І. М.", year=2023))

    s1, _ = Section.objects.get_or_create(grade=g5, number=1, defaults={"name_uk": "Розділ I. Натуральні числа", "textbook": tb5})
    Section.objects.get_or_create(grade=g5, number=2, defaults={"name_uk": "Розділ II. Дроби", "textbook": tb5})
    p1, _ = Paragraph.objects.get_or_create(section=s1, number=1, defaults={"name_uk": "§ 1. Натуральні числа"})
    s6, _ = Section.objects.get_or_create(grade=g6, number=1, defaults={"name_uk": "Розділ 1. Подільність чисел", "textbook": tb6})
    Paragraph.objects.get_or_create(section=s6, number=1, defaults={"name_uk": "§ 1. Дільники і кратні"})

    item, created = Item.objects.get_or_create(paragraph=p1, number=3, defaults={"content": "3. Відрізок. Довжина відрізка"})
    for n, title in [(1, "Ряд натуральних чисел"), (2, "Цифри. Десятковий запис")]:
        Item.objects.get_or_create(paragraph=p1, number=n, defaults={"content": f"{n}. {title}"})
    if created:
        ContentBlock.objects.create(item=item, block_type="theory", order=1, text=THEORY)
        block = ContentBlock.objects.create(item=item, block_type="exercise", order=2)
        ex = Exercise.objects.create(textbook=tb5, block=block, number=78, order=1, difficulty="preparatory",
                                     condition="Знайдіть довжину відрізка AC, якщо точка B лежить між A і C:")
        for k, (text, ans) in enumerate([("AB = 8 см, BC = 5 см;", "13"), ("AB = 12 мм, BC = 9 мм.", "21")], start=1):
            sub = SubExercise.objects.create(exercise=ex, number=str(k), order=k, text=text)
            Answer.objects.create(exercise=ex, subexercise=sub, kind="book", text=ans)
        ContentBlock.objects.create(item=item, block_type="wise_owl", order=3,
                                    text="Чи можна на прямій позначити три точки так, щоб кожна лежала між двома іншими?")
    return item


if __name__ == "__main__":
    lesson = seed()
    print(f"seed_ui: готово (урок id={lesson.pk})")
