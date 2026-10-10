"""Розмір pipeline_cache/ по підручниках і очищення.

    python manage.py clean_pipeline_cache                      # таблиця розмірів, нічого не видаляє
    python manage.py clean_pipeline_cache --yes                # видалити prep/ (оброблені сторінки; відновлюються самі)
    python manage.py clean_pipeline_cache --parts prep,pages --yes
    python manage.py clean_pipeline_cache --include-unknown --yes   # також кеші PDF, яких немає в БД

Частини: prep — безпечно; pages — сторінки відновляться з PDF, але /review/ без них покаже вирізки лише
якщо PDF лежить за шляхом з БД; ocr — дорогий (Tesseract годинами), видаляй лише свідомо.
vision/ (відповіді й бюджет Gemini) ніколи не чіпається.
"""
from django.core.management.base import BaseCommand, CommandError

from education import cache_tools as ct
from education.models import Textbook
from education.pdf_pipeline.config import PipelineConfig


class Command(BaseCommand):
    help = "Показує розмір pipeline_cache/ і чистить кеш обробки сторінок"

    def add_arguments(self, parser):
        parser.add_argument("--parts", default=",".join(ct.DEFAULT_PARTS), help="що чистити: prep,pages,ocr")
        parser.add_argument("--include-unknown", action="store_true", help="чистити й кеші PDF, яких немає в БД")
        parser.add_argument("--yes", action="store_true", help="справді видалити (без цього лише таблиця)")

    def handle(self, *args, **opts):
        parts = tuple(p.strip() for p in opts["parts"].split(",") if p.strip())
        bad = [p for p in parts if p not in ct.PARTS]
        if bad or not parts:
            raise CommandError(f"Невідомі частини {bad or parts}; можна: {', '.join(ct.PARTS)}")
        cache_dir = PipelineConfig.from_env_file().cache_dir
        if not cache_dir.is_dir():
            self.stdout.write(f"Кешу немає: {cache_dir}")
            return
        known = dict(Textbook.objects.values_list("pdf_sha256", "profile_code"))
        entries = ct.scan(cache_dir, known)

        self.stdout.write(f"{'Підручник':<22}{'sha':<10}" + "".join(f"{p:>11}" for p in ct.PARTS) + f"{'разом':>11}")
        for e in entries:
            self.stdout.write(f"{e.label:<22}{e.sha[:8]:<10}" + "".join(f"{ct.human(e.sizes[p]):>11}" for p in ct.PARTS)
                              + f"{ct.human(e.total):>11}")
        other = ct.other_size(cache_dir, entries)
        total = sum(e.total for e in entries)
        self.stdout.write(f"Інше (vision/, бюджети — не чіпається): {ct.human(other)}; усього в {cache_dir}: {ct.human(total + other)}")

        target = [e for e in entries if e.known or opts["include_unknown"]]
        would = sum(e.sizes[p] for e in target for p in parts)
        if not opts["yes"]:
            self.stdout.write(self.style.NOTICE(
                f"Нічого не видалено. З --yes буде видалено {', '.join(parts)} ({ct.human(would)})."))
            skipped = [e for e in entries if not e.known and not opts["include_unknown"]]
            if skipped:
                self.stdout.write(f"Кеші без запису в БД ({len(skipped)}) пропущено; додай --include-unknown, щоб їх теж.")
            return
        freed = ct.clear(entries, parts, include_unknown=opts["include_unknown"])
        self.stdout.write(self.style.SUCCESS(f"Звільнено {ct.human(freed)} ({', '.join(parts)})"))
