from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import Answer, ContentBlock, Exercise, Paragraph, SubExercise, Textbook

# Оригінальний демо-контент (без підручника) для §1,2,4-11 розділу I «Натуральні числа і
# дії над ними. Вирази. Рівняння» (5 клас, import_mon_grade5). §3 вже наповнений окремо,
# через demo_mon_topics.
TOPICS = [
    {
        "paragraph": 1, "condition": "Дай відповідь.",
        "theory": (
            "Натуральні числа — числа, якими рахують предмети (1, 2, 3, ...); число нуль "
            "також належить до натуральних. Для запису чисел використовують десять цифр: "
            "0, 1, ..., 9. Значення цифри в записі числа залежить від її розряду (місця) — "
            "це десятковий запис."
        ),
        "exercises": [
            ("1) Скільки цифр використовують для запису будь-якого натурального числа?", "10"),
            ("2) Яка цифра стоїть у розряді сотень числа 4827?", "8"),
            ("3) Чи є число 0 натуральним числом?", "так"),
        ],
    },
    {
        "paragraph": 2, "condition": "Порівняй.",
        "theory": (
            "З двох натуральних чисел більше те, що має більше цифр; якщо кількість цифр "
            "однакова — більше те, у якого більший старший розряд. Порівняння записують "
            "знаками >, < або =."
        ),
        "exercises": [
            ("1) Яке число більше: 358 чи 385? Запиши більше число.", "385"),
            ("2) Яке число менше: 999 чи 1000? Запиши менше число.", "999"),
            ("3) Чи правда, що 207 > 270?", "ні"),
        ],
    },
    {
        "paragraph": 4, "condition": "Обчисли.",
        "theory": (
            "Різниця — результат віднімання. Від'ємник не може бути більшим за зменшуване. "
            "Перевірка віднімання: якщо додати різницю і від'ємник, має вийти зменшуване."
        ),
        "exercises": [("1) 15 - 6", "9"), ("2) 100 - 37", "63"), ("3) 254 - 198", "56")],
    },
    {
        "paragraph": 5, "condition": "Обчисли.",
        "theory": (
            "Числовий вираз складається з чисел, з'єднаних знаками дій. Буквений вираз містить "
            "літери, що позначають довільні числа. Формула — рівність, яка задає правило "
            "обчислення однієї величини через інші (наприклад, периметр квадрата P = 4a)."
        ),
        "exercises": [
            ("1) Значення виразу 3a + 2, якщо a = 5", "17"),
            ("2) Периметр квадрата P = 4a. Знайди P, якщо a = 6", "24"),
            ("3) 7 + 2 * 3 (спочатку множення)", "13"),
        ],
    },
    {
        "paragraph": 6, "condition": "Розв'яжи рівняння.",
        "theory": (
            "Рівняння — рівність із невідомим числом (змінною), яке треба знайти. Невідомий "
            "доданок: від суми віднімають відомий доданок. Невідомий від'ємник: від зменшуваного "
            "віднімають різницю. Невідоме зменшуване: додають різницю і від'ємник."
        ),
        "exercises": [("1) x + 7 = 12", "5"), ("2) 20 - x = 8", "12"), ("3) x - 9 = 16", "25")],
    },
    {
        "paragraph": 7, "condition": "Обчисли.",
        "theory": (
            "Добуток — результат множення. Переставна властивість: від перестановки множників "
            "добуток не змінюється (a * b = b * a)."
        ),
        "exercises": [
            ("1) 6 * 7", "42"),
            ("2) Зручним способом: 25 * 13 * 4", "1300"),
            ("3) 9 * 8", "72"),
        ],
    },
    {
        "paragraph": 8, "condition": "Обчисли.",
        "theory": (
            "Сполучна властивість множення: (a*b)*c = a*(b*c) — множники можна групувати "
            "по-різному. Розподільна властивість: a*(b+c) = a*b + a*c."
        ),
        "exercises": [
            ("1) Зручним способом: 2 * 37 * 5", "370"),
            ("2) Розподільною властивістю: 6 * (10 + 3)", "78"),
            ("3) 4 * (20 + 5)", "100"),
        ],
    },
    {
        "paragraph": 9, "condition": "Дай відповідь.",
        "theory": (
            "Частка — результат ділення. Ділене : дільник = частка. Перевірка: частка * "
            "дільник = ділене. Ділити на нуль не можна."
        ),
        "exercises": [
            ("1) 84 : 4", "21"),
            ("2) 144 : 12", "12"),
            ("3) Чи можна ділити число на нуль?", "ні"),
        ],
    },
    {
        "paragraph": 10, "condition": "Дай відповідь.",
        "theory": (
            "Якщо число не ділиться націло, отримують неповну частку й остачу: "
            "ділене = дільник * неповна частка + остача. Остача завжди менша за дільник."
        ),
        "exercises": [
            ("1) 17 : 5 — яка остача?", "2"),
            ("2) 23 : 4 — яка неповна частка?", "5"),
            ("3) Чи може остача дорівнювати дільнику?", "ні"),
        ],
    },
    {
        "paragraph": 11, "condition": "Обчисли.",
        "theory": "Квадрат числа — добуток числа самого на себе: a² = a * a. Куб числа: a³ = a * a * a.",
        "exercises": [("1) 5²", "25"), ("2) 3³", "27"), ("3) 10²", "100")],
    },
]


class Command(BaseCommand):
    help = ("Додає оригінальну теорію та вправи для §1,2,4-11 розділу I «Натуральні числа і "
           "дії над ними. Вирази. Рівняння» (5 клас, import_mon_grade5).")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            textbook = Textbook.objects.get(profile_code="mon_grade5")
        except Textbook.DoesNotExist:
            raise CommandError("Спочатку виконай: python manage.py import_mon_grade5")

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

        self.stdout.write(self.style.SUCCESS(f"Готово: контент для {len(TOPICS)} параграфів (Розділ I, 5 клас)."))
