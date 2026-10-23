from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import Answer, ContentBlock, Exercise, Paragraph, SubExercise, Textbook

# Оригінальний демо-контент (без підручника) для розділу III «Відношення і пропорції»
# (6 клас, import_mon_grade6) -- усі 6 §.
TOPICS = [
    {
        "paragraph": 1, "condition": "Обчисли.",
        "theory": (
            "Відношення чисел a і b (b не дорівнює 0) — частка a : b; показує, у скільки "
            "разів a більше за b (або яку частину a становить від b). Масштаб — "
            "відношення довжини на кресленні (карті) до реальної довжини."
        ),
        "exercises": [
            ("1) Відношення чисел 10 і 2", "5"),
            ("2) Масштаб карти 1:1000000. Відстань на карті 3 см. Яка реальна відстань у км?", "30"),
            ("3) Відношення чисел 15 і 5", "3"),
        ],
    },
    {
        "paragraph": 2, "condition": "Дай відповідь.",
        "theory": (
            "Пропорція — рівність двох відношень: a : b = c : d. Основна властивість "
            "пропорції: добуток крайніх членів дорівнює добутку середніх (a * d = b * c)."
        ),
        "exercises": [
            ("1) Знайди x: x : 4 = 6 : 8", "3"),
            ("2) Знайди x: 3 : x = 9 : 12", "4"),
            ("3) Чи правильна пропорція 2:3 = 8:12?", "так"),
        ],
    },
    {
        "paragraph": 3, "condition": "Знайди відсоткове відношення.",
        "theory": (
            "Відсоткове відношення числа a до числа b показує, скільки відсотків "
            "становить a від b: (a : b) * 100%."
        ),
        "exercises": [
            ("1) Число 25 до числа 50", "50"),
            ("2) Число 3 до числа 12", "25"),
            ("3) Число 10 до числа 10", "100"),
        ],
    },
    {
        "paragraph": 4, "condition": "Дай відповідь.",
        "theory": (
            "Величини прямо пропорційні, якщо зі збільшенням однієї в кілька разів інша "
            "збільшується у стільки ж разів. Обернено пропорційні — якщо інша у стільки ж "
            "разів зменшується."
        ),
        "exercises": [
            ("1) 5 зошитів коштують 25 грн. Скільки коштують 8 таких зошитів?", "40"),
            ("2) 4 робітники виконують роботу за 12 днів. За скільки днів виконають ту саму роботу 6 робітників?", "8"),
            ("3) Авто долає шлях за 2 год зі швидкістю 60 км/год. За скільки годин подолає той самий шлях зі швидкістю 40 км/год?", "3"),
        ],
    },
    {
        "paragraph": 5, "condition": "Поділи число у заданому відношенні.",
        "theory": (
            "Щоб поділити число у відношенні m:n, його ділять на (m+n) рівних частин і "
            "беруть m частин для першого числа, n — для другого."
        ),
        "exercises": [
            ("1) Поділи 20 у відношенні 2:3. Яке менше число?", "8"),
            ("2) Поділи 40 у відношенні 1:3. Яке більше число?", "30"),
            ("3) Поділи 24 у відношенні 1:2. Яке менше число?", "8"),
        ],
    },
    {
        "paragraph": 6, "condition": "Дай відповідь.",
        "theory": "Діаграма — наочний спосіб подання даних (стовпчикова, кругова тощо).",
        "exercises": [
            ("1) Чи використовують стовпчикову діаграму для порівняння величин?", "так"),
            ("2) У класі 30 учнів: 12 хлопців, решта дівчат. Скільки дівчат?", "18"),
            ("3) Один стовпчик удвічі вищий за інший; менший відповідає 15. Яке значення більшого?", "30"),
        ],
    },
]


class Command(BaseCommand):
    help = "Додає оригінальну теорію та вправи для розділу III «Відношення і пропорції» (6 клас, import_mon_grade6)."

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            textbook = Textbook.objects.get(profile_code="mon_grade6")
        except Textbook.DoesNotExist:
            raise CommandError("Спочатку виконай: python manage.py import_mon_grade6")

        for topic in TOPICS:
            paragraph = Paragraph.objects.get(section__textbook=textbook, section__number=3, number=topic["paragraph"])
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

        self.stdout.write(self.style.SUCCESS(f"Готово: контент для {len(TOPICS)} параграфів (Розділ III, 6 клас)."))
