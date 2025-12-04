#education/management/commands/import_curriculum.py
from django.core.management.base import BaseCommand
from ai.curriculum_importer import import_curriculum_to_db

class Command(BaseCommand):
    help = "Імпорт навчальної програми у базу даних"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("🔄 Починаємо імпорт навчальної програми..."))
        import_curriculum_to_db()
        self.stdout.write(self.style.SUCCESS("✅ Імпорт завершено успішно!"))
