"""Завантажує ручні виправлення з CSV (export_review_queue) → text_source="manual".

    python manage.py import_review_fixes --csv review/review_queue.csv [--dry-run]

new_text — новий текст (умова вправи або текст підпункту);
reviewed = 1/так/x — «перевірено, усе правильно» (текст не міняється).
Виправлені записи отримують text_source="manual" і needs_review=False, тож наступний
import_textbook їх не перезапише. Для обчислювальних підпунктів вираз і відповідь перераховуються.
"""
import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education.models import Answer, Exercise, SubExercise

YES = {"1", "так", "x", "х", "yes", "y", "+", "ok"}


class Command(BaseCommand):
    help = "Імпортує ручні правки з CSV черги перевірки"

    def add_arguments(self, parser):
        parser.add_argument("--csv", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        path = Path(opts["csv"])
        if not path.is_file():
            raise CommandError(f"Файл не знайдено: {path}")
        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        missing = {"kind", "id", "new_text", "reviewed"} - set(rows[0] if rows else {})
        if missing:
            raise CommandError(f"У CSV немає колонок: {sorted(missing)}")

        changed = reviewed = skipped = 0
        errors = []
        with transaction.atomic():
            for line, row in enumerate(rows, start=2):
                new_text = (row.get("new_text") or "").strip()
                ok = (row.get("reviewed") or "").strip().lower() in YES
                if not new_text and not ok:
                    skipped += 1
                    continue
                model = {"exercise": Exercise, "subexercise": SubExercise}.get(row["kind"])
                obj = model.objects.filter(pk=row["id"]).first() if model and row["id"].isdigit() else None
                if obj is None:
                    errors.append(f"рядок {line}: {row['kind']} #{row['id']} не знайдено")
                    continue
                if new_text:
                    self.apply_text(obj, new_text)
                    changed += 1
                else:
                    reviewed += 1
                obj.text_source, obj.needs_review = "manual", False
                obj.save()
            if opts["dry_run"]:
                transaction.set_rollback(True)

        for err in errors:
            self.stdout.write(self.style.WARNING(err))
        prefix = "DRY-RUN: " if opts["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}виправлено {changed}, підтверджено {reviewed}, "
                                             f"пропущено {skipped}, помилок {len(errors)}"))

    @staticmethod
    def apply_text(obj, new_text):
        if isinstance(obj, Exercise):
            obj.condition = new_text
            return
        obj.text = new_text
        exercise = obj.exercise
        if exercise.task_verb != "compute":
            return
        from education.pdf_pipeline.math_text import analyze_expression
        result = analyze_expression(new_text, natural_numbers=exercise.textbook.grade.number <= 5)
        obj.expr, obj.expr_status, obj.expr_issues = result.expression, result.status, result.issues
        Answer.objects.filter(exercise=exercise, subexercise=obj, kind="computed").delete()
        if result.answer is not None:
            Answer.objects.create(exercise=exercise, subexercise=obj, kind="computed", text=result.answer)
            book = Answer.objects.filter(exercise=exercise, subexercise=obj, kind="book").first()
            if book is not None:
                obj.answer_check = "verified" if book.value_numeric == Answer.objects.get(
                    exercise=exercise, subexercise=obj, kind="computed").value_numeric else "mismatch"
