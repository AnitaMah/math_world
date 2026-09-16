"""
Replaces import_programm_csv: imports a curriculum table of contents
straight from a plain-text file (no hand-made CSV step) into
Grade -> Section -> Paragraph -> Item.

Usage:
    python manage.py import_curriculum --file data/5_class_ukr.txt \\
        --grade 5 --language uk [--subject math] [--reset]

--subject selects the SubjectProfile that knows how to read this
particular curriculum's headings (see education/parsing/subject_profiles.py).
Use "math" for a Розділ/§/numbered-lesson textbook, or "generic" for a
subject with no such structure (every paragraph of text becomes one item).

Step 20 also wires the Step 15-19 content-block classifiers into this same
command as a dry run, so there's one place to run curriculum imports from:

    python manage.py import_curriculum --dry-run \\
        --content-file review/section_1_text/combined.txt

--dry-run prints the ContentBlocks the classifiers would create for
--content-file's raw OCR text, in document order, without writing anything
to the database. --file/--grade are not required in this mode.
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import Grade, Item, Paragraph, Section, Subject
from education.parsing.content_classifier import collect_content_block_previews
from education.parsing.subject_profiles import get_profile
from education.parsing.toc_parser import parse_toc


class Command(BaseCommand):
    help = (
        "Імпортує зміст підручника (Розділ/§/пункти) напряму з текстового "
        "файлу у структуру Grade -> Section -> Paragraph -> Item. Також "
        "підтримує --dry-run для попереднього перегляду ContentBlock(ів), "
        "розпізнаних класифікаторами Step 15-19, без запису у БД."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", required=False, help="Шлях до txt-файлу зі змістом підручника"
        )
        parser.add_argument(
            "--grade", type=int, required=False, help="Клас, напр. 5"
        )
        parser.add_argument(
            "--language",
            choices=["uk", "de"],
            default="uk",
            help="Мова заголовків і контенту, що імпортується",
        )
        parser.add_argument(
            "--subject",
            default="math",
            help="Профіль парсингу: math, ukr_language, generic (див. subject_profiles.py)",
        )
        parser.add_argument(
            "--subject-code",
            default=None,
            help=(
                "Код предмета (Subject.code) для цього класу, напр. 'math'. "
                "Якщо не вказано, використовується те саме значення, що й --subject."
            ),
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Видалити попередній вміст цього класу перед імпортом",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Запустити класифікатори контент-блоків (Step 15-19) над "
                "--content-file і вивести результат без запису у БД."
            ),
        )
        parser.add_argument(
            "--content-file",
            default=None,
            help="Шлях до сирого OCR-тексту для --dry-run",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            self._handle_dry_run(options)
            return

        if not options["file"]:
            raise CommandError("--file обов'язковий (крім --dry-run)")
        if not options["grade"]:
            raise CommandError("--grade обов'язковий (крім --dry-run)")

        file_path = Path(options["file"])
        grade_number = options["grade"]
        lang = options["language"]
        profile = get_profile(options["subject"])
        subject_code = options["subject_code"] or options["subject"]

        if not file_path.exists():
            raise CommandError(f"Файл не знайдено: {file_path}")

        name_field = "name_uk" if lang == "uk" else "name_de"
        content_field = "content" if lang == "uk" else "content_de"

        lines = file_path.read_text(encoding="utf-8").splitlines()
        sections_data, skipped = parse_toc(lines, profile)

        if not sections_data:
            raise CommandError(
                "Не вдалося розпізнати жодного розділу чи пункту у файлі -- "
                "перевірте формат вхідного тексту або оберіть інший --subject профіль."
            )

        with transaction.atomic():
            subject, subject_created = Subject.objects.get_or_create(
                code=subject_code,
                defaults={"name_uk": subject_code},
            )
            if subject_created:
                self.stdout.write(
                    self.style.WARNING(
                        f"ℹ️ Створено новий Subject(code={subject_code!r}) з тимчасовою "
                        f"назвою -- задайте нормальну name_uk/name_de в адмінці."
                    )
                )

            # Grade is now scoped by (number, subject): the same grade
            # number can exist once per subject (e.g. two separate
            # "5 клас" rows, one for math and one for ukr_mova).
            grade, _ = Grade.objects.get_or_create(
                number=grade_number,
                subject=subject,
                defaults={name_field: f"{grade_number} клас"},
            )
            if not getattr(grade, name_field):
                setattr(grade, name_field, f"{grade_number} клас")
                grade.save(update_fields=[name_field])

            if options["reset"]:
                Section.objects.filter(grade=grade).delete()

            section_count = paragraph_count = item_count = 0

            for sec_rec in sections_data:
                section, _ = Section.objects.update_or_create(
                    grade=grade,
                    number=sec_rec.number,
                    defaults={name_field: sec_rec.title},
                )
                section_count += 1

                for para_rec in sec_rec.paragraphs:
                    paragraph, _ = Paragraph.objects.update_or_create(
                        section=section,
                        number=para_rec.number,
                        defaults={name_field: para_rec.title},
                    )
                    paragraph_count += 1

                    for item_rec in para_rec.items:
                        Item.objects.update_or_create(
                            paragraph=paragraph,
                            number=item_rec.number,
                            defaults={content_field: item_rec.content},
                        )
                        item_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Клас {grade_number} ({lang}): "
                f"{section_count} розділів, {paragraph_count} параграфів, "
                f"{item_count} пунктів."
            )
        )
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"ℹ️ Пропущено {len(skipped)} службових рядків "
                    f"(Завдання/Головне/Зміст/Відповіді тощо) -- це очікувано."
                )
            )

    def _handle_dry_run(self, options):
        content_file = options["content_file"]
        if not content_file:
            raise CommandError("--dry-run вимагає --content-file <шлях до сирого OCR-тексту>")

        content_path = Path(content_file)
        if not content_path.exists():
            raise CommandError(f"Файл не знайдено: {content_path}")

        raw_text = content_path.read_text(encoding="utf-8")
        previews = collect_content_block_previews(raw_text)

        self.stdout.write(
            f"Знайдено {len(previews)} ContentBlock(ів) з {content_path} "
            f"(DRY RUN -- нічого не записано в БД):\n"
        )
        for preview in previews:
            tag = f" [{preview['difficulty']}]" if preview["difficulty"] else ""
            text = preview["text"]
            if len(text) > 200:
                text = text[:200] + "…"
            self.stdout.write(
                f"  #{preview['order']:>3} {preview['block_type']}{tag} "
                f"(рядок {preview['start_line']}): {text}"
            )
