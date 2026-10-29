"""Демо-контент МОН: теорія і вправи з автоперевіркою для одного розділу (без підручника).

    python manage.py demo_mon_seed --grade 5 --section 1
    python manage.py demo_mon_seed --grade 6 --section 4

Замінює 9 окремих команд demo_mon_grade5_section1..4 / demo_mon_grade6_section1..5
(byte-for-byte той самий контент і логіка -- об'єднано, бо Django не підтримує
команди в підпапках management/commands/, тож 9 майже ідентичних файлів лише
роздували папку; сам контент -- education/management/mon_content/grade5.py,
grade6.py). §3 5 класу і 2 теми (demo_mon_topics) наповнені окремо.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.management.mon_content import grade5, grade6
from education.models import Answer, ContentBlock, Exercise, Paragraph, SubExercise, Textbook

CONTENT = {5: grade5.SECTIONS, 6: grade6.SECTIONS}
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}


class Command(BaseCommand):
    help = "Додає оригінальну теорію та вправи з автоперевіркою для розділу програми МОН (import_mon_curriculum)."

    def add_arguments(self, parser):
        parser.add_argument("--grade", type=int, required=True, choices=sorted(CONTENT),
                            help="клас (5 або 6)")
        parser.add_argument("--section", type=int, required=True, help="номер розділу")

    @transaction.atomic
    def handle(self, *args, **options):
        grade, section = options["grade"], options["section"]
        topics = CONTENT[grade].get(section)
        if topics is None:
            available = ", ".join(str(n) for n in sorted(CONTENT[grade]))
            raise CommandError(f"Немає демо-контенту для {grade} класу, розділу {section} "
                               f"(є: {available})")
        try:
            textbook = Textbook.objects.get(profile_code=f"mon_grade{grade}")
        except Textbook.DoesNotExist:
            raise CommandError(f"Спочатку виконай: python manage.py import_mon_grade{grade}")

        for topic in topics:
            paragraph = Paragraph.objects.get(section__textbook=textbook, section__number=section,
                                              number=topic["paragraph"])
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

        roman = ROMAN.get(section, str(section))
        self.stdout.write(self.style.SUCCESS(
            f"Готово: контент для {len(topics)} параграфів (Розділ {roman}, {grade} клас)."))
