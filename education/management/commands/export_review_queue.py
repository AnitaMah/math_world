"""CSV з вправами й підпунктами, які чекають ручної перевірки (needs_review).

    python manage.py export_review_queue --textbook math_merzlyak_5 --out review/queue.csv

Відкрий у Excel/LibreOffice, заповни колонку new_text (або reviewed = 1, якщо все правильно)
і завантаж назад: python manage.py import_review_fixes --csv review/queue.csv
"""
import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from education.models import Exercise, SubExercise, Textbook

FIELDS = ["kind", "id", "textbook", "exercise", "sub", "page", "reason", "text", "new_text", "reviewed"]


def find_textbook(value):
    qs = Textbook.objects.filter(pk=int(value)) if str(value).isdigit() else Textbook.objects.filter(profile_code=value)
    tb = qs.first()
    if tb is None:
        raise CommandError(f"Підручник {value!r} не знайдено (id або profile_code)")
    return tb


class Command(BaseCommand):
    help = "Експортує чергу needs_review у CSV для ручної правки"

    def add_arguments(self, parser):
        parser.add_argument("--textbook", help="id або profile_code; за замовчуванням — усі")
        parser.add_argument("--out", default="review/review_queue.csv")
        parser.add_argument("--all", action="store_true", help="усі вправи, а не лише needs_review")

    def handle(self, *args, **opts):
        exercises = Exercise.objects.select_related("textbook", "block").order_by("textbook", "source_page", "order")
        subs = SubExercise.objects.select_related("exercise__textbook").order_by("exercise__textbook", "exercise__source_page", "order")
        if opts["textbook"]:
            tb = find_textbook(opts["textbook"])
            exercises, subs = exercises.filter(textbook=tb), subs.filter(exercise__textbook=tb)
        if not opts["all"]:
            exercises, subs = exercises.filter(needs_review=True), subs.filter(needs_review=True)

        out = Path(opts["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        rows = 0
        with out.open("w", encoding="utf-8-sig", newline="") as fh:          # utf-8-sig — щоб Excel бачив кирилицю
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            for ex in exercises:
                writer.writerow({"kind": "exercise", "id": ex.pk, "textbook": ex.textbook.profile_code,
                                 "exercise": ex.number, "sub": "", "page": ex.source_page or "",
                                 "reason": ",".join(ex.flags or []) or ex.answer_check, "text": ex.condition,
                                 "new_text": "", "reviewed": ""})
                rows += 1
            for sub in subs:
                reason = sub.expr_status + (f": {','.join(sub.expr_issues)}" if sub.expr_issues else "")
                writer.writerow({"kind": "subexercise", "id": sub.pk, "textbook": sub.exercise.textbook.profile_code,
                                 "exercise": sub.exercise.number, "sub": sub.number,
                                 "page": sub.exercise.source_page or "", "reason": reason, "text": sub.text,
                                 "new_text": "", "reviewed": ""})
                rows += 1
        self.stdout.write(self.style.SUCCESS(f"{rows} рядків → {out}"))
