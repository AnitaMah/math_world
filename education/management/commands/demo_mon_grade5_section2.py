from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import Answer, ContentBlock, Exercise, Paragraph, SubExercise, Textbook

# Оригінальний демо-контент (без підручника) для §2-5 розділу II «Звичайні дроби»
# (5 клас, import_mon_grade5). §1 вже наповнений окремо, через demo_mon_topics.
TOPICS = [
    {
        "paragraph": 2,   # Правильні і неправильні дроби. Порівняння дробів
        "condition": "Визнач.",
        "theory": (
            "Дріб правильний, якщо його чисельник менший за знаменник (дріб менший за 1). "
            "Дріб неправильний, якщо чисельник більший або дорівнює знаменнику (дріб не менший за 1). "
            "Дроби з однаковим знаменником порівнюють за чисельником: більший той дріб, у якого більший чисельник."
        ),
        "exercises": [
            ("1) Яка дріб більша: 5/9 чи 2/9? Запиши більший дріб.", "5/9"),
            ("2) Чи правильний дріб 3/5?", "так"),
            ("3) Чи правильний дріб 9/4?", "ні"),
        ],
    },
    {
        "paragraph": 3,   # Додавання і віднімання дробів з однаковими знаменниками
        "condition": "Обчисли.",
        "theory": (
            "Щоб додати (відняти) дроби з однаковим знаменником, додають (віднімають) їхні "
            "чисельники, а знаменник лишають тим самим."
        ),
        "exercises": [("1) 2/7 + 3/7", "5/7"), ("2) 5/8 - 2/8", "3/8"), ("3) 1/6 + 1/6 + 1/6", "1/2")],
    },
    {
        "paragraph": 4,   # Звичайні дроби і ділення натуральних чисел
        "condition": "Запиши частку у вигляді дробу.",
        "theory": (
            "Частку a : b (a, b — натуральні числа, b не дорівнює 0) можна записати дробом a/b: "
            "a — чисельник, b — знаменник."
        ),
        "exercises": [("1) 3 : 4", "3/4"), ("2) 7 : 2", "7/2"), ("3) 5 : 5", "1")],
    },
    {
        "paragraph": 5,   # Мішані числа
        "condition": "Запиши мішане число у вигляді неправильного дробу.",
        "theory": (
            "Мішане число складається з цілої та дробової частини, наприклад 2 1/3 означає 2 + 1/3. "
            "Щоб перетворити мішане число в неправильний дріб: цілу частину множать на знаменник і "
            "додають чисельник — це новий чисельник, знаменник лишається той самий."
        ),
        "exercises": [("1) 2 1/3", "7/3"), ("2) 3 2/5", "17/5"), ("3) 1 1/2", "3/2")],
    },
]


class Command(BaseCommand):
    help = "Додає оригінальну теорію та вправи для §2-5 розділу II «Звичайні дроби» (5 клас, import_mon_grade5)."

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            textbook = Textbook.objects.get(profile_code="mon_grade5")
        except Textbook.DoesNotExist:
            raise CommandError("Спочатку виконай: python manage.py import_mon_grade5")

        for topic in TOPICS:
            paragraph = Paragraph.objects.get(section__textbook=textbook, section__number=2, number=topic["paragraph"])
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

        self.stdout.write(self.style.SUCCESS(f"Готово: контент для {len(TOPICS)} параграфів (Розділ II, 5 клас)."))
