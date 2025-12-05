from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from education.models import Grade, Section, Paragraph, Item


ROMAN_MAP = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}


def roman_to_int(value: str) -> int:
    total = 0
    previous = 0
    for char in value.upper():
        current = ROMAN_MAP.get(char, 0)
        if current > previous:
            total += current - 2 * previous
        else:
            total += current
        previous = current
    return total if total > 0 else 0


class Command(BaseCommand):
    help = (
        "Import curriculum text files into Grade/Section/Paragraph/Item models. "
        "Accepts a single --file or scans a directory for '*_class_*.txt' files."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", help="Path to a single curriculum .txt file")
        parser.add_argument(
            "--directory",
            default="data",
            help="Directory with one or more '*_class_*.txt' files",
        )
        parser.add_argument("--grade", type=int, help="Grade number for --file")
        parser.add_argument(
            "--language",
            default="uk",
            help="Language code (stored on the grade name for now)",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                "Скинути існуючі дані цього класу перед імпортом: видаляє клас та"
                " всі його розділи/параграфи/пункти, після чого завантажує файл"
            ),
        )

    def handle(self, *args, **options):
        file_path = options.get("file")
        directory = options.get("directory")
        grade_override = options.get("grade")
        language = options.get("language")

        files = self._discover_files(file_path, directory)
        if not files:
            raise CommandError("Не знайдено жодного файлу для імпорту.")

        for path in files:
            grade_number = grade_override or self._infer_grade(path)
            if not grade_number:
                raise CommandError(
                    f"Не вдалось визначити клас з назви файлу '{path.name}'. Додайте --grade."
                )
            self.stdout.write(f"➡️  Імпорт класу {grade_number} з файлу {path}")
            self._import_file(path, grade_number, language, reset=options.get("reset"))

    def _discover_files(self, file_path: str | None, directory: str) -> list[Path]:
        if file_path:
            return [Path(file_path)]
        base = Path(directory)
        if not base.exists():
            return []
        return sorted(base.glob("*_class_*.txt"))

    def _infer_grade(self, path: Path) -> int | None:
        match = re.search(r"(\d+)_class", path.name)
        return int(match.group(1)) if match else None

    def _import_file(self, path: Path, grade_number: int, language: str, reset: bool) -> None:
        lines = path.read_text(encoding="utf-8").splitlines()

        # Імпорт може починатися з будь-якої мови, тому задаємо обидва поля,
        # щоб уникнути помилки через обов'язкове name_uk/content.
        grade_defaults = {
            "name_uk": f"{grade_number} клас",
            "name_de": f"Klasse {grade_number}",
        }

        if reset:
            deleted, _ = Grade.objects.filter(number=grade_number).delete()
            if deleted:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ⚠️  Видалено існуючі записи класу {grade_number} перед повторним імпортом"
                    )
                )

        grade, _ = Grade.objects.get_or_create(number=grade_number, defaults=grade_defaults)

        if language == "uk" and not grade.name_uk:
            grade.name_uk = f"{grade_number} клас"
        if language == "de" and not grade.name_de:
            grade.name_de = f"Klasse {grade_number}"
        grade.save()

        current_section = None
        current_paragraph = None
        current_item = None
        section_count = paragraph_count = item_count = 0

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            section_match = re.match(r"^Розділ\s+([IVXLCDM]+)\.\s*(.*)$", line)
            if section_match:
                section_count += 1
                section_title = section_match.group(2).strip() or line
                section_number = roman_to_int(section_match.group(1)) or section_count
                section_defaults = {"name_uk": section_title, "name_de": section_title}
                current_section, _ = Section.objects.get_or_create(
                    grade=grade,
                    number=section_number,
                    defaults=section_defaults,
                )
                if language == "uk":
                    current_section.name_uk = section_title
                else:
                    current_section.name_de = section_title
                current_section.save()
                current_paragraph = None
                current_item = None
                self.stdout.write(f"  • Розділ {section_number}: {section_title}")
                continue

            paragraph_match = re.match(r"^§\s*(\d+)\.\s*(.*)$", line)
            if paragraph_match and current_section:
                paragraph_count += 1
                paragraph_number = int(paragraph_match.group(1))
                paragraph_title = paragraph_match.group(2).strip() or line
                paragraph_defaults = {"name_uk": paragraph_title, "name_de": paragraph_title}
                current_paragraph, _ = Paragraph.objects.get_or_create(
                    section=current_section,
                    number=paragraph_number,
                    defaults=paragraph_defaults,
                )
                if language == "uk":
                    current_paragraph.name_uk = paragraph_title
                else:
                    current_paragraph.name_de = paragraph_title
                current_paragraph.save()
                current_item = None
                self.stdout.write(f"    ◦ Параграф {paragraph_number}: {paragraph_title}")
                continue

            item_match = re.match(r"^(\d+)\.\s*(.*)$", line)
            if item_match and current_paragraph:
                item_count += 1
                item_number = int(item_match.group(1))
                item_text = item_match.group(2).strip() or line
                defaults = {"content": item_text, "content_de": item_text}
                current_item, _ = Item.objects.get_or_create(
                    paragraph=current_paragraph,
                    number=item_number,
                    defaults=defaults,
                )
                if language == "uk":
                    current_item.content = item_text
                else:
                    current_item.content_de = item_text
                current_item.save()
                continue

            bullet_match = re.match(r"^[•\-]\s*(.*)$", line)
            if bullet_match and current_item:
                extra = bullet_match.group(1).strip()
                field = "content_de" if language == "de" else "content"
                existing = getattr(current_item, field) or ""
                setattr(current_item, field, f"{existing}\n• {extra}".strip())
                current_item.save(update_fields=[field])
                continue

            if current_item:
                field = "content_de" if language == "de" else "content"
                existing = getattr(current_item, field) or ""
                setattr(current_item, field, f"{existing}\n{line}".strip())
                current_item.save(update_fields=[field])

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: {section_count} розділів, {paragraph_count} параграфів, {item_count} пунктів."
            )
        )
