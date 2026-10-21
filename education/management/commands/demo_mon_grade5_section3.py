from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import Answer, ContentBlock, Exercise, Paragraph, SubExercise, Textbook

# Оригінальний демо-контент (без підручника) для розділу III «Десяткові дроби» (5 клас,
# import_mon_grade5) -- усі 9 §.
TOPICS = [
    {
        "paragraph": 1, "condition": "Запиши десятковим дробом.",
        "theory": (
            "Десятковий дріб — дріб зі знаменником 10, 100, 1000 тощо, записаний без "
            "знаменника через кому: 7/10 = 0,7; 25/100 = 0,25. Цифри після коми — "
            "десяткові розряди (десяті, соті, тисячні)."
        ),
        "exercises": [
            ("1) Дріб 7/10", "0,7"),
            ("2) Дріб 25/100", "0,25"),
            ("3) Скільки цифр стоїть після коми в дробі 3,142?", "3"),
        ],
    },
    {
        "paragraph": 2, "condition": "Порівняй.",
        "theory": (
            "Щоб порівняти десяткові дроби, спершу порівнюють цілі частини; якщо вони "
            "рівні — порівнюють десяті, потім соті тощо."
        ),
        "exercises": [
            ("1) Яке число більше: 0,7 чи 0,65? Запиши більше число.", "0,7"),
            ("2) Яке число менше: 3,04 чи 3,4? Запиши менше число.", "3,04"),
            ("3) Чи правда, що 2,5 = 2,50?", "так"),
        ],
    },
    {
        "paragraph": 3, "condition": "Округли.",
        "theory": (
            "Щоб округлити число до певного розряду, дивляться на наступну цифру: 0-4 — "
            "попередню лишають без змін, 5-9 — збільшують на 1. Цифри після розряду "
            "округлення відкидають."
        ),
        "exercises": [
            ("1) 3,47 до десятих", "3,5"),
            ("2) 128 до десятків", "130"),
            ("3) 5,238 до сотих", "5,24"),
        ],
    },
    {
        "paragraph": 4, "condition": "Обчисли.",
        "theory": "Десяткові дроби додають і віднімають «стовпчиком», підписуючи кому під комою.",
        "exercises": [("1) 2,3 + 1,45", "3,75"), ("2) 5 - 1,2", "3,8"), ("3) 0,6 + 0,4", "1")],
    },
    {
        "paragraph": 5, "condition": "Обчисли.",
        "theory": (
            "Щоб перемножити десяткові дроби, їх множать як натуральні числа, не зважаючи "
            "на коми, а в добутку відокремлюють комою стільки цифр справа, скільки їх було "
            "після ком в обох множниках разом."
        ),
        "exercises": [("1) 0,5 * 4", "2"), ("2) 1,2 * 0,3", "0,36"), ("3) 2,5 * 2", "5")],
    },
    {
        "paragraph": 6, "condition": "Обчисли.",
        "theory": (
            "Щоб поділити число на десятковий дріб, у діленому й дільнику переносять кому "
            "вправо на стільки цифр, скільки їх після коми в дільнику, а тоді ділять як "
            "натуральні числа."
        ),
        "exercises": [("1) 4,8 : 2", "2,4"), ("2) 6 : 0,5", "12"), ("3) 1,25 : 5", "0,25")],
    },
    {
        "paragraph": 7, "condition": "Обчисли.",
        "theory": "Середнє арифметичне кількох чисел — їх сума, поділена на кількість доданків.",
        "exercises": [
            ("1) Середнє арифметичне чисел 4, 6, 8", "6"),
            ("2) Середнє арифметичне чисел 10, 20", "15"),
            ("3) Середнє арифметичне чисел 2, 3, 4, 5", "3,5"),
        ],
    },
    {
        "paragraph": 8, "condition": "Знайди відсоток від числа.",
        "theory": (
            "Відсоток — сота частина числа (1% = 0,01). Щоб знайти кілька відсотків від "
            "числа, число множать на відповідний десятковий дріб (20% від a = 0,2 * a)."
        ),
        "exercises": [
            ("1) 10% від 200", "20"),
            ("2) 50% від 80", "40"),
            ("3) 25% від 40", "10"),
        ],
    },
    {
        "paragraph": 9, "condition": "Знайди число за його відсотком.",
        "theory": (
            "Щоб знайти число за його відсотком, значення відсотка ділять на відповідний "
            "десятковий дріб (якщо 20% числа дорівнює b, саме число = b : 0,2)."
        ),
        "exercises": [
            ("1) 20% числа дорівнює 10. Знайди число.", "50"),
            ("2) 25% числа дорівнює 12. Знайди число.", "48"),
            ("3) 10% числа дорівнює 7. Знайди число.", "70"),
        ],
    },
]


class Command(BaseCommand):
    help = "Додає оригінальну теорію та вправи для розділу III «Десяткові дроби» (5 клас, import_mon_grade5)."

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            textbook = Textbook.objects.get(profile_code="mon_grade5")
        except Textbook.DoesNotExist:
            raise CommandError("Спочатку виконай: python manage.py import_mon_grade5")

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

        self.stdout.write(self.style.SUCCESS(f"Готово: контент для {len(TOPICS)} параграфів (Розділ III, 5 клас)."))
