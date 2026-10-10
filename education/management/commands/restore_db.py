"""Відкат бази з автобекапу (backups/, див. education/backup.py).

    python manage.py restore_db                      # список копій
    python manage.py restore_db --latest             # що буде зроблено (нічого не змінює)
    python manage.py restore_db --latest --yes       # відкотити до найновішої копії
    python manage.py restore_db --file db_20261010_131241.sqlite3 --yes

Поточну базу перед відкатом зберігає як backups/before_restore_*.sqlite3 (3 останні), тож відкат теж можна скасувати.
Закрий runserver і shell перед відкатом.
"""
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from education import backup


def human_size(path):
    return f"{path.stat().st_size / 1024 / 1024:.1f} МБ"


class Command(BaseCommand):
    help = "Список копій БД і відкат до однієї з них"

    def add_arguments(self, parser):
        parser.add_argument("--latest", action="store_true", help="найновіша копія")
        parser.add_argument("--file", help="ім'я копії з backups/ або шлях до файлу")
        parser.add_argument("--yes", action="store_true", help="справді виконати відкат")

    def handle(self, *args, **opts):
        if not opts["latest"] and not opts["file"]:
            return self.list_backups()
        try:
            path = backup.resolve_backup(opts["file"])
            exercises = backup.check_backup(path)
        except backup.BackupError as exc:
            raise CommandError(str(exc)) from exc
        when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m.%Y %H:%M:%S")
        self.stdout.write(f"Копія: {path.name} ({when}, {human_size(path)}, вправ у ній: {exercises})")
        if not opts["yes"]:
            self.stdout.write(self.style.NOTICE("Нічого не змінено. Додай --yes, щоб відкотити базу до цієї копії."))
            return
        try:
            safety = backup.restore(path)
        except backup.BackupError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Базу відкочено. Попередній стан збережено: {safety}"))

    def list_backups(self):
        found = backup.list_backups()
        if not found:
            self.stdout.write(f"У {backup.backup_dir()} немає копій (вони створюються при import_textbook).")
            return
        for i, p in enumerate(found):
            when = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d.%m.%Y %H:%M:%S")
            self.stdout.write(f"{'*' if i == 0 else ' '} {p.name}  {when}  {human_size(p)}")
        self.stdout.write("* — найновіша. Відкат: python manage.py restore_db --latest --yes")
