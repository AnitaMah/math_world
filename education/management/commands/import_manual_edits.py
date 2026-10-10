"""Застосовує JSON з export_manual_edits до поточної БД (ідемпотентно).

    python manage.py import_manual_edits --json review/manual_edits.json [--dry-run]
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from education import review
from education.models import Textbook


class Command(BaseCommand):
    help = "Застосовує ручні правки з JSON"

    def add_arguments(self, parser):
        parser.add_argument("--json", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        path = Path(opts["json"])
        if not path.is_file():
            raise CommandError(f"Файл не знайдено: {path}")
        edits = json.loads(path.read_text(encoding="utf-8")).get("edits", [])
        done = unchanged = 0
        missing = []
        with transaction.atomic():
            for e in edits:
                tb = Textbook.objects.filter(profile_code=e["profile_code"]).first()
                obj = review.find_object(tb, e["kind"], e["block_type"], e["number"], e["page"], e.get("sub", "")) if tb else None
                if obj is None:
                    missing.append(f"{e['profile_code']} №{e['number']} {e.get('sub', '')} стор. {e['page']}")
                    continue
                if e["action"] == "skip":
                    state = (obj.review_skipped, obj.needs_review)
                    review.skip(obj)
                    changed = state != (True, True)
                elif e["action"] == "unskip":
                    changed = obj.review_skipped
                    if changed:
                        review.unskip(obj)
                else:
                    changed = review.text_of(obj) != e["text"] or obj.needs_review or obj.text_source != "manual"
                    if changed:
                        review.save_edit(obj, e["text"])
                done += changed
                unchanged += not changed
            if opts["dry_run"]:
                transaction.set_rollback(True)
        for m in missing:
            self.stdout.write(self.style.WARNING(f"не знайдено: {m}"))
        prefix = "DRY-RUN: " if opts["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}застосовано {done}, без змін {unchanged}, не знайдено {len(missing)}"))
