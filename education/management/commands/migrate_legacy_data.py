"""Міграція старих даних (21В.2): звіт, порівняння з копією БД, видалення старих блоків, backfill.

    python manage.py migrate_legacy_data                         # лише звіт, нічого не змінює
    python manage.py migrate_legacy_data --compare-db db.backup.sqlite3 [--markdown review/compare.md]
    python manage.py migrate_legacy_data --apply                 # видалити старі блоки + Section.textbook

Старі блоки видаляються лише в уроках, де вже є нові, і не ті, що правилися вручну.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education import legacy


class Command(BaseCommand):
    help = "Звіт і очищення даних, що лишилися від старого імпорту"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="виконати зміни (за замовчуванням — лише звіт)")
        parser.add_argument("--compare-db", help="sqlite-копія БД зі СТАРИМИ блоками для таблиці різниць")
        parser.add_argument("--all-old", action="store_true",
                            help="у --compare-db брати всі блоки, а не лише без source_page")
        parser.add_argument("--markdown", help="куди записати таблицю порівняння (.md)")

    def handle(self, *args, **opts):
        out = self.stdout.write
        if opts["compare_db"]:
            db = Path(opts["compare_db"])
            if not db.is_file():
                raise CommandError(f"Файл не знайдено: {db}")
            old = legacy.old_block_counts(str(db), only_legacy=not opts["all_old"])
            new = legacy.new_block_counts()
            rows = legacy.compare(old, new)
            md = legacy.comparison_markdown(rows, sum(old.values()), sum(new.values()), db.name)
            if opts["markdown"]:
                Path(opts["markdown"]).write_text(md, encoding="utf-8")
                out(f"Таблицю записано в {opts['markdown']}")
            else:
                out(md)

        with transaction.atomic():
            rep = legacy.audit(apply=opts["apply"])
        prefix = "ЗАСТОСОВАНО" if opts["apply"] else "ЗВІТ (нічого не змінено)"
        out(self.style.MIGRATE_HEADING(prefix))
        out(f"Старих блоків (без source_page): {rep.legacy_blocks}"
            f" → {'видалено' if opts['apply'] else 'можна видалити'}: {rep.deletable};"
            f" лишено, бо в уроці ще немає нових: {rep.kept_no_new}; лишено, бо правилися вручну: {rep.kept_manual}")
        out(f"Розділів: {rep.sections_total}, без підручника: {rep.sections_without_textbook}"
            f" (backfill {'виконано' if opts['apply'] else 'можливий'} для {rep.sections_backfillable})")
        for grade, number in rep.sections_orphan:
            out(self.style.WARNING(f"  розділ {number} класу {grade}: для класу немає (єдиного) Textbook — лишається як є"))
        out(f"Пунктів: {rep.items_total}, без підручника: {rep.items_without_textbook}")
        for code, st in rep.by_textbook.items():
            out(f"  {code}: розділів {st['sections']}, пунктів {st['items']}, блоків {st['blocks']}, вправ {st['exercises']}")
