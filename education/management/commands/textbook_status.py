"""Стан підручників у БД: скільки вправ, скільки чекають перевірки, останній імпорт.

    python manage.py textbook_status
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from education.models import Exercise, SubExercise, Textbook


class Command(BaseCommand):
    help = "Підручники в БД: вправи, needs_review, звірка з відповідями, останній імпорт"

    def handle(self, *args, **opts):
        books = Textbook.objects.select_related("grade").order_by("grade__number", "title")
        if not books:
            self.stdout.write("Підручників ще немає. Див.: python manage.py parse_textbook --help")
            return
        for tb in books:
            ex = Exercise.objects.filter(textbook=tb).aggregate(
                total=Count("id"), review=Count("id", filter=Q(needs_review=True)),
                manual=Count("id", filter=Q(text_source="manual")), oral=Count("id", filter=Q(block__block_type="oral_exercise")))
            subs = SubExercise.objects.filter(exercise__textbook=tb).aggregate(
                total=Count("id"), review=Count("id", filter=Q(needs_review=True)),
                verified=Count("id", filter=Q(answer_check="verified")),
                mismatch=Count("id", filter=Q(answer_check="mismatch")))
            mism = (SubExercise.objects.filter(exercise__textbook=tb, answer_check="mismatch")
                    .values("exercise__block__item__paragraph__number", "exercise__block__paragraph__number")
                    .annotate(n=Count("id")))
            by_par = {}
            for row in mism:
                par = row["exercise__block__item__paragraph__number"] or row["exercise__block__paragraph__number"]
                by_par[par] = by_par.get(par, 0) + row["n"]
            run = tb.import_runs.first()
            pct = 100 * ex["review"] / ex["total"] if ex["total"] else 0
            self.stdout.write(self.style.MIGRATE_HEADING(f"#{tb.pk} {tb} — {tb.grade.number} клас [{tb.profile_code}]"))
            self.stdout.write(f"  вправ: {ex['total']} (усних {ex['oral']}), на перевірку: {ex['review']} ({pct:.0f}%), "
                              f"виправлено вручну: {ex['manual']}")
            self.stdout.write(f"  підпунктів: {subs['total']}, на перевірку: {subs['review']}, "
                              f"відповідь збіглась: {subs['verified']}, не збіглась: {subs['mismatch']}")
            if by_par:
                self.stdout.write("  розбіжності з відповідями книги: "
                                  + ", ".join(f"§{p}: {n}" for p, n in sorted(by_par.items(), key=lambda kv: kv[0] or 0)))
            if run:
                self.stdout.write(f"  останній імпорт: {run.started_at:%Y-%m-%d %H:%M} — {run.get_status_display()}"
                                  + (f" ({run.message[:80]})" if run.status == "failed" else ""))
            else:
                self.stdout.write("  імпортів не було")
