from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import Answer, ContentBlock, Exercise, Paragraph, SubExercise, Textbook

# Оригінальний демо-контент (без підручника) для розділу V «Геометричні фігури і
# величини» (6 клас, import_mon_grade6) -- усі 5 §. Без рисунків.
TOPICS = [
    {
        "paragraph": 1, "condition": "Дай відповідь.",
        "theory": (
            "Коло — множина всіх точок площини, рівновіддалених від однієї точки "
            "(центра). Круг — частина площини, обмежена колом. Радіус — відстань від "
            "центра до точки кола. Діаметр — відрізок через центр, що з'єднує дві точки "
            "кола (d = 2r). Круговий сектор — частина круга, обмежена двома радіусами і "
            "дугою."
        ),
        "exercises": [
            ("1) Радіус кола 5 см. Який діаметр?", "10"),
            ("2) Діаметр кола 18 см. Який радіус?", "9"),
            ("3) Чи є круг частиною площини?", "так"),
        ],
    },
    {
        "paragraph": 2, "condition": "Обчисли (π ≈ 3,14).",
        "theory": "Довжина кола C = 2πr. Площа круга S = πr² (π ≈ 3,14).",
        "exercises": [
            ("1) Радіус кола 10 см. Яка довжина кола?", "62,8"),
            ("2) Радіус круга 10 см. Яка площа круга?", "314"),
            ("3) Радіус кола 5 см. Яка довжина кола?", "31,4"),
        ],
    },
    {
        "paragraph": 3, "condition": "Дай відповідь.",
        "theory": (
            "Циліндр має дві паралельні рівні кругові основи і бічну поверхню. Конус має "
            "одну кругову основу і вершину. Куля — множина точок простору на однаковій "
            "відстані від центра (основ не має)."
        ),
        "exercises": [
            ("1) Скільки основ має циліндр?", "2"),
            ("2) Скільки основ має конус?", "1"),
            ("3) Чи має куля основи?", "ні"),
        ],
    },
    {
        "paragraph": 4, "condition": "Дай відповідь.",
        "theory": "Дві прямі перпендикулярні, якщо вони перетинаються під прямим кутом (90°).",
        "exercises": [
            ("1) Під яким кутом перетинаються перпендикулярні прямі?", "90"),
            ("2) Чи є перпендикулярні прямі паралельними?", "ні"),
            ("3) Чи можуть дві перпендикулярні прямі перетинатися більше ніж в одній точці?", "ні"),
        ],
    },
    {
        "paragraph": 5, "condition": "Дай відповідь.",
        "theory": "Дві прямі на площині паралельні, якщо вони не перетинаються (скільки б їх не продовжували).",
        "exercises": [
            ("1) Чи перетинаються паралельні прямі?", "ні"),
            ("2) Чи можуть дві різні прямі бути одночасно паралельними і перпендикулярними?", "ні"),
            ("3) Чи лежать паралельні прямі в одній площині?", "так"),
        ],
    },
]


class Command(BaseCommand):
    help = "Додає оригінальну теорію та вправи для розділу V «Геометричні фігури і величини» (6 клас, import_mon_grade6)."

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            textbook = Textbook.objects.get(profile_code="mon_grade6")
        except Textbook.DoesNotExist:
            raise CommandError("Спочатку виконай: python manage.py import_mon_grade6")

        for topic in TOPICS:
            paragraph = Paragraph.objects.get(section__textbook=textbook, section__number=5, number=topic["paragraph"])
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

        self.stdout.write(self.style.SUCCESS(f"Готово: контент для {len(TOPICS)} параграфів (Розділ V, 6 клас)."))
