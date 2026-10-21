from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import Answer, ContentBlock, Exercise, Paragraph, SubExercise, Textbook

# Оригінальний демо-контент (без підручника) для розділу II «Звичайні дроби» (6 клас,
# import_mon_grade6) -- усі 10 §.
TOPICS = [
    {
        "paragraph": 1, "condition": "Скороти дріб.",
        "theory": (
            "Основна властивість дробу: якщо чисельник і знаменник помножити (або "
            "поділити) на одне й те саме натуральне число, дріб не зміниться. Скоротити "
            "дріб — поділити чисельник і знаменник на їх спільний дільник."
        ),
        "exercises": [("1) 6/8", "3/4"), ("2) 15/20", "3/4"), ("3) 9/27", "1/3")],
    },
    {
        "paragraph": 2, "condition": "Дай відповідь.",
        "theory": (
            "Найменший спільний знаменник (НСЗ) дробів — найменше спільне кратне їхніх "
            "знаменників. Щоб звести дріб до нового знаменника, чисельник і знаменник "
            "множать на одне й те саме число (додатковий множник)."
        ),
        "exercises": [
            ("1) НСЗ дробів 1/4 і 1/6", "12"),
            ("2) Яка дріб більша: 2/3 чи 3/5? Запиши більший дріб.", "2/3"),
            ("3) Зведи 1/3 до знаменника 12. Який чисельник?", "4"),
        ],
    },
    {
        "paragraph": 3, "condition": "Обчисли.",
        "theory": (
            "Щоб додати (відняти) дроби з різними знаменниками, спочатку зводять їх до "
            "спільного знаменника, а потім додають (віднімають) чисельники."
        ),
        "exercises": [("1) 1/2 + 1/3", "5/6"), ("2) 3/4 - 1/2", "1/4"), ("3) 2/3 + 1/6", "5/6")],
    },
    {
        "paragraph": 4, "condition": "Обчисли.",
        "theory": "Щоб перемножити дроби, перемножують чисельники і перемножують знаменники.",
        "exercises": [("1) 2/3 * 3/4", "1/2"), ("2) 1/2 * 1/5", "1/10"), ("3) 3/5 * 5/6", "1/2")],
    },
    {
        "paragraph": 5, "condition": "Знайди дріб від числа.",
        "theory": "Щоб знайти дріб від числа, число множать на цей дріб.",
        "exercises": [("1) 2/3 від 15", "10"), ("2) 3/4 від 20", "15"), ("3) 1/5 від 45", "9")],
    },
    {
        "paragraph": 6, "condition": "Обчисли.",
        "theory": (
            "Два числа взаємно обернені, якщо їх добуток дорівнює 1 (наприклад, 2/3 і "
            "3/2). Щоб поділити на дріб, множать на обернений до нього дріб."
        ),
        "exercises": [
            ("1) Яке число обернене до 3/5?", "5/3"),
            ("2) 2/3 : 4/5", "5/6"),
            ("3) 1/2 : 1/4", "2"),
        ],
    },
    {
        "paragraph": 7, "condition": "Знайди число.",
        "theory": "Щоб знайти число за значенням його дробу, значення ділять на цей дріб.",
        "exercises": [
            ("1) 2/3 числа дорівнює 10. Знайди число.", "15"),
            ("2) 3/4 числа дорівнює 9. Знайди число.", "12"),
            ("3) 1/5 числа дорівнює 7. Знайди число.", "35"),
        ],
    },
    {
        "paragraph": 8, "condition": "Перетвори у десятковий дріб.",
        "theory": "Щоб перетворити звичайний дріб у десятковий, чисельник ділять на знаменник.",
        "exercises": [("1) 1/4", "0,25"), ("2) 3/5", "0,6"), ("3) 1/2", "0,5")],
    },
    {
        "paragraph": 9, "condition": "Дай відповідь.",
        "theory": (
            "Якщо дріб не перетворюється в скінченний десятковий, отримують нескінченний "
            "періодичний дріб (наприклад, 1/3 = 0,333...). Групу цифр, що повторюється, "
            "називають періодом."
        ),
        "exercises": [
            ("1) Чи є дріб 1/3 = 0,333... нескінченним періодичним?", "так"),
            ("2) Період дробу 1/3 = 0,(3) — одна цифра. Яка?", "3"),
            ("3) Чи є 0,5 нескінченним періодичним дробом?", "ні"),
        ],
    },
    {
        "paragraph": 10, "condition": "Округли.",
        "theory": (
            "Якщо звичайний дріб не можна точно записати скінченним десятковим, його "
            "наближено округлюють до потрібного розряду."
        ),
        "exercises": [
            ("1) 1/3 ≈ 0,333... до сотих", "0,33"),
            ("2) 2/3 ≈ 0,666... до десятих", "0,7"),
            ("3) 1/7 ≈ 0,142857... до сотих", "0,14"),
        ],
    },
]


class Command(BaseCommand):
    help = "Додає оригінальну теорію та вправи для розділу II «Звичайні дроби» (6 клас, import_mon_grade6)."

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            textbook = Textbook.objects.get(profile_code="mon_grade6")
        except Textbook.DoesNotExist:
            raise CommandError("Спочатку виконай: python manage.py import_mon_grade6")

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

        self.stdout.write(self.style.SUCCESS(f"Готово: контент для {len(TOPICS)} параграфів (Розділ II, 6 клас)."))
