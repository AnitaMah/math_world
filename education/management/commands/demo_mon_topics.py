from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import Answer, ContentBlock, Exercise, Paragraph, SubExercise, Textbook

# Оригінальний демо-контент (без підручника) для 2 реальних тем програми МОН --
# показує теорію + вправи з автоперевіркою поверх import_mon_grade5.
TOPICS = [
    {
        "section": 1, "paragraph": 3,   # Додавання натуральних чисел. Властивості додавання
        "theory": (
            "Сума — результат додавання. Переставна властивість: від зміни місць доданків "
            "сума не змінюється (a + b = b + a). Сполучна властивість: доданки можна групувати "
            "по-різному (a + b + c = a + (b + c))."
        ),
        "exercises": [("1) 3 + 5", "8"), ("2) 127 + 48", "175"), ("3) 25 + 17 + 75", "117")],
    },
    {
        "section": 2, "paragraph": 1,   # Уявлення про звичайні дроби
        "theory": (
            "Звичайний дріб записують у вигляді a/b, де a — чисельник (скільки частин взяли), "
            "b — знаменник (на скільки рівних частин поділили ціле). Наприклад, 3/4 означає: "
            "ціле поділили на 4 рівні частини і взяли 3 з них."
        ),
        "exercises": [("1) 1/2 від 10", "5"), ("2) 3/4 від 20", "15"), ("3) 2/5 від 25", "10")],
    },
]


class Command(BaseCommand):
    help = "Додає оригінальну теорію та вправи з автоперевіркою до 2 тем програми МОН (import_mon_grade5)."

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            textbook = Textbook.objects.get(profile_code="mon_grade5")
        except Textbook.DoesNotExist:
            raise CommandError("Спочатку виконай: python manage.py import_mon_grade5")

        for topic in TOPICS:
            paragraph = Paragraph.objects.get(
                section__textbook=textbook, section__number=topic["section"], number=topic["paragraph"]
            )
            paragraph.content_blocks.all().delete()

            ContentBlock.objects.create(paragraph=paragraph, block_type="theory", order=0, text=topic["theory"])
            ex_block = ContentBlock.objects.create(paragraph=paragraph, block_type="exercise", order=1, title="Вправи")
            exercise = Exercise.objects.create(
                textbook=textbook, block=ex_block, number=topic["paragraph"], order=0,
                difficulty="medium", condition="Обчисли.",
            )
            for sub_idx, (text, answer) in enumerate(topic["exercises"], start=1):
                sub = SubExercise.objects.create(exercise=exercise, number=str(sub_idx), order=sub_idx, text=text)
                Answer.objects.create(exercise=exercise, subexercise=sub, kind="book", text=answer)

            self.stdout.write(self.style.SUCCESS(f"Розділ {topic['section']} § {topic['paragraph']}: {paragraph.name_uk}"))

        self.stdout.write(self.style.SUCCESS(f"Готово: демо-контент для {len(TOPICS)} тем."))
