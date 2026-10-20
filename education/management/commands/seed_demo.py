import hashlib

from django.core.management.base import BaseCommand
from django.db import transaction

from education.models import (
    Answer, ContentBlock, Exercise, Grade, Paragraph, Section, SubExercise, Subject, Textbook,
)

# Original demo content (no textbook material) — just enough to exercise the map,
# lesson and answer-checking flow end to end.
SECTIONS = [
    {
        "name": "Додавання і віднімання",
        "paragraphs": [
            {
                "name": "Додавання натуральних чисел",
                "theory": "Сума чисел — це результат додавання. Наприклад, сума чисел 3 і 5 дорівнює 8.",
                "exercises": [("1) 3 + 5", "8"), ("2) 12 + 7", "19"), ("3) 20 + 15", "35")],
            },
            {
                "name": "Віднімання натуральних чисел",
                "theory": "Різниця чисел — це результат віднімання. Різниця чисел 10 і 4 дорівнює 6.",
                "exercises": [("1) 10 - 4", "6"), ("2) 25 - 9", "16")],
            },
        ],
    },
    {
        "name": "Множення і ділення",
        "paragraphs": [
            {
                "name": "Таблиця множення",
                "theory": "Добуток чисел — це результат множення. Добуток чисел 6 і 7 дорівнює 42.",
                "exercises": [("1) 6 * 7", "42"), ("2) 8 * 9", "72")],
            },
            {
                "name": "Ділення без залишку",
                "theory": "Частка чисел — це результат ділення. Частка чисел 36 і 6 дорівнює 6.",
                "exercises": [("1) 36 / 6", "6"), ("2) 81 / 9", "9")],
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Створює невеликий демонстраційний клас (оригінальний контент, без підручника) для демо застосунку."

    def add_arguments(self, parser):
        parser.add_argument("--grade-number", type=int, default=5)

    @transaction.atomic
    def handle(self, *args, **options):
        grade_number = options["grade_number"]

        subject, _ = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})
        grade, _ = Grade.objects.get_or_create(
            subject=subject, number=grade_number, defaults={"name_uk": f"{grade_number} клас"}
        )
        sha = hashlib.sha256(f"math-world-demo-grade-{grade_number}".encode()).hexdigest()
        textbook, _ = Textbook.objects.get_or_create(
            pdf_sha256=sha,
            defaults=dict(
                subject=subject, grade=grade, profile_code="demo",
                title="Демо-курс Math World", author="Math World", year=2026,
            ),
        )

        for s_idx, section_data in enumerate(SECTIONS, start=1):
            section, _ = Section.objects.update_or_create(
                grade=grade, textbook=textbook, number=s_idx, defaults={"name_uk": section_data["name"]}
            )
            for p_idx, para_data in enumerate(section_data["paragraphs"], start=1):
                paragraph, _ = Paragraph.objects.update_or_create(
                    section=section, number=p_idx, defaults={"name_uk": para_data["name"]}
                )
                paragraph.content_blocks.all().delete()

                ContentBlock.objects.create(
                    paragraph=paragraph, block_type="theory", order=0, text=para_data["theory"],
                )
                ex_block = ContentBlock.objects.create(
                    paragraph=paragraph, block_type="exercise", order=1, title="Вправи",
                )
                exercise = Exercise.objects.create(
                    textbook=textbook, block=ex_block, number=p_idx, order=0,
                    difficulty="medium", condition="Обчисли.",
                )
                for sub_idx, (text, answer) in enumerate(para_data["exercises"], start=1):
                    sub = SubExercise.objects.create(
                        exercise=exercise, number=str(sub_idx), order=sub_idx, text=text,
                    )
                    Answer.objects.create(exercise=exercise, subexercise=sub, kind="book", text=answer)

        self.stdout.write(self.style.SUCCESS(
            f"Демо-клас {grade_number} готовий: {len(SECTIONS)} розділи, "
            f"{sum(len(s['paragraphs']) for s in SECTIONS)} уроки."
        ))
