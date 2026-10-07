"""textbook.json → БД (ідемпотентно; ручні правки не перезаписуються).

    python manage.py import_textbook --json pipeline_out/math_merzlyak_5/textbook.json --dry-run
    python manage.py import_textbook --json pipeline_out/math_merzlyak_5/textbook.json
"""
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from education.importers.textbook_json import MODELS, TextbookImporter

COLUMNS = ("created", "updated", "deleted", "unchanged", "kept_manual")


class Command(BaseCommand):
    help = "Імпортує textbook.json (результат parse_textbook) у базу даних"

    def add_arguments(self, parser):
        parser.add_argument("--json", required=True, help="шлях до textbook.json")
        parser.add_argument("--dry-run", action="store_true", help="порахувати зміни і нічого не записати")
        parser.add_argument("--reset", action="store_true", help="перестворити блоки уроків з JSON (ручні — лишаються)")

    def handle(self, *args, **opts):
        path = Path(opts["json"])
        if not path.is_file():
            raise CommandError(f"Файл не знайдено: {path}")
        try:
            result = TextbookImporter.from_file(path, dry_run=opts["dry_run"], reset=opts["reset"]).run()
        except ValidationError as exc:
            raise CommandError(f"Невалідний JSON: {'; '.join(exc.messages)}") from exc
        except Exception as exc:  # noqa: BLE001 — ImportRun(failed) уже записано імпортером
            raise CommandError(f"Імпорт не вдався ({type(exc).__name__}: {exc}); зміни відкочено") from exc

        self.stdout.write(self.format_table(result.as_stats()))
        for warning in result.warnings:
            self.stdout.write(self.style.WARNING(f"⚠ {warning}"))
        if result.dry_run:
            self.stdout.write(self.style.NOTICE("DRY-RUN: нічого не записано"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Готово: Textbook #{result.textbook_id}, ImportRun #{result.import_run_id}"))

    @staticmethod
    def format_table(stats):
        header = f"{'':<13}" + "".join(f"{c:>12}" for c in COLUMNS)
        rows = [f"{m:<13}" + "".join(f"{stats[m][c]:>12}" for c in COLUMNS) for m in MODELS if m in stats]
        return "\n".join([header, *rows])
