"""Вивантажує ручні правки (журнал ManualEdit) у JSON — щоб застосувати до свіжої БД.

    python manage.py export_manual_edits --out review/manual_edits.json [--textbook math_merzlyak_5]

Для кожного ключа (підручник + тип блоку + номер + сторінка + підпункт) береться остання дія.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand

from education.management.commands.export_review_queue import find_textbook
from education.models import ManualEdit


def latest_edits(textbook=None):
    qs = ManualEdit.objects.select_related("textbook").order_by("created_at", "pk")
    if textbook:
        qs = qs.filter(textbook=textbook)
    latest = {}
    for e in qs:
        latest[(e.textbook.profile_code, e.kind, e.block_type, e.exercise_number, e.source_page, e.sub_number)] = e
    return [{"profile_code": e.textbook.profile_code, "kind": e.kind, "block_type": e.block_type,
             "number": e.exercise_number, "page": e.source_page, "sub": e.sub_number,
             "action": e.action, "text": e.new_text} for e in latest.values()]


class Command(BaseCommand):
    help = "Експортує останні ручні правки в JSON"

    def add_arguments(self, parser):
        parser.add_argument("--out", default="review/manual_edits.json")
        parser.add_argument("--textbook")

    def handle(self, *args, **opts):
        tb = find_textbook(opts["textbook"]) if opts["textbook"] else None
        rows = latest_edits(tb)
        out = Path(opts["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"version": 1, "edits": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"{len(rows)} правок → {out}"))
