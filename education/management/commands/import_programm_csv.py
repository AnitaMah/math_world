import csv
import os

from django.core.management.base import BaseCommand
from education.models import Grade, Section, Paragraph, Item

class Command(BaseCommand):
    help = 'Імпортує програму з CSV-файлу для вказаного класу та мови'

    def add_arguments(self, parser):
        parser.add_argument('filename', type=str, help='Назва CSV-файлу в папці programm/')
        parser.add_argument('--grade', type=int, required=True, help='Клас (напр. 5)')
        parser.add_argument('--lang', type=str, choices=['uk', 'de'], default='uk', help='Мова: uk або de')

    def handle(self, *args, **options):
        grade_number = options['grade']
        lang = options['lang']
        section_field = f"name_{lang}"
        paragraph_field = f"name_{lang}"
        content_field = 'content' if lang == 'uk' else 'content_de'

        filename = options['filename']
        file_path = os.path.join('programm', filename)

        if not os.path.exists(file_path):
            self.stderr.write(f"❌ Файл не знайдено: {file_path}")
            return

        try:
            with open(file_path, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                grade, _ = Grade.objects.get_or_create(number=grade_number)

                sections = {}

                for row in reader:
                    if int(row["grade"]) != grade_number:
                        continue

                    section_number = int(row["section_number"])
                    section_name = row["section"].strip()
                    lesson_number = int(row["lesson_number"])
                    lesson_title = row["lesson_title"].strip()

                    section_key = (section_number, section_name)
                    if section_key not in sections:
                        section, _ = Section.objects.get_or_create(
                            grade=grade,
                            number=section_number,
                            defaults={section_field: section_name}
                        )
                        sections[section_key] = section
                    else:
                        section = sections[section_key]

                    paragraph, _ = Paragraph.objects.get_or_create(
                        section=section,
                        number=lesson_number,
                        defaults={paragraph_field: lesson_title}
                    )

                    Item.objects.get_or_create(
                        paragraph=paragraph,
                        number=1,
                        defaults={content_field: lesson_title}
                    )

                self.stdout.write(self.style.SUCCESS(f"✅ Імпорт завершено для класу {grade_number}, мова: {lang}"))

        except Exception as e:
            self.stderr.write(f"❌ Помилка: {e}")
