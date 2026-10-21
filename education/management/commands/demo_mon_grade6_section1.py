from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import Answer, ContentBlock, Exercise, Paragraph, SubExercise, Textbook

# Оригінальний демо-контент (без підручника) для розділу I «Подільність чисел» (6 клас,
# import_mon_grade6) -- усі 4 §.
TOPICS = [
    {
        "paragraph": 1, "condition": "Дай відповідь.",
        "theory": (
            "Дільник числа a — число, на яке a ділиться націло. Кратне числа a — число, "
            "яке ділиться на a націло (само a, 2a, 3a, ...)."
        ),
        "exercises": [
            ("1) Чи є число 4 дільником числа 20?", "так"),
            ("2) Чи є число 7 дільником числа 20?", "ні"),
            ("3) Найменше натуральне кратне числа 6, більше за 10.", "12"),
        ],
    },
    {
        "paragraph": 2, "condition": "Дай відповідь.",
        "theory": (
            "На 10 діляться числа, що закінчуються на 0. На 5 — ті, що закінчуються на 0 "
            "або 5. На 2 — парні числа. На 9 — числа, сума цифр яких ділиться на 9. "
            "На 3 — числа, сума цифр яких ділиться на 3."
        ),
        "exercises": [
            ("1) Чи ділиться число 345 на 5?", "так"),
            ("2) Чи ділиться число 128 на 9?", "ні"),
            ("3) Чи ділиться число 123 на 3?", "так"),
        ],
    },
    {
        "paragraph": 3, "condition": "Дай відповідь.",
        "theory": (
            "Просте число має рівно два дільники — 1 і само себе (2, 3, 5, 7, 11, ...). "
            "Складене число має більше двох дільників. Число 1 — ні просте, ні складене. "
            "Будь-яке складене число можна розкласти в добуток простих множників."
        ),
        "exercises": [
            ("1) Чи є число 7 простим?", "так"),
            ("2) Чи є число 9 простим?", "ні"),
            ("3) Число 12 = 2 * 2 * 3. Скільки простих множників (з повтореннями)?", "3"),
        ],
    },
    {
        "paragraph": 4, "condition": "Обчисли.",
        "theory": (
            "НСД (найбільший спільний дільник) двох чисел — найбільше число, на яке обидва "
            "числа діляться націло. НСК (найменше спільне кратне) — найменше число, яке "
            "ділиться на обидва числа."
        ),
        "exercises": [("1) НСД чисел 12 і 18", "6"), ("2) НСК чисел 4 і 6", "12"), ("3) НСД чисел 7 і 9", "1")],
    },
]


class Command(BaseCommand):
    help = "Додає оригінальну теорію та вправи для розділу I «Подільність чисел» (6 клас, import_mon_grade6)."

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            textbook = Textbook.objects.get(profile_code="mon_grade6")
        except Textbook.DoesNotExist:
            raise CommandError("Спочатку виконай: python manage.py import_mon_grade6")

        for topic in TOPICS:
            paragraph = Paragraph.objects.get(section__textbook=textbook, section__number=1, number=topic["paragraph"])
            paragraph.content_blocks.all().delete()

            ContentBlock.objects.create(paragraph=paragraph, block_type="theory", order=0, text=topic["theory"])
            ex_block = ContentBlock.objects.create(paragraph=paragraph, block_type="exercise", order=1, title="Вправи")
            exercise = Exercise.objects.create(
                textbook=textbook, block=ex_block, number=topic["paragraph"], order=0,
                difficulty="medium", condition=topic["condition"],
            )
            for sub_idx, (text, answer) in enumerate(topic["exercises"], start=1):
                sub = SubExercise.objects.create(exercise=exercise, number=str(sub_idx), order=sub_idx, text=text)
                Answer.objects.create(exercise=exercise, subexercise=sub, kind="book", text=answer)

            self.stdout.write(self.style.SUCCESS(f"§ {topic['paragraph']}: {paragraph.name_uk}"))

        self.stdout.write(self.style.SUCCESS(f"Готово: контент для {len(TOPICS)} параграфів (Розділ I, 6 клас)."))
