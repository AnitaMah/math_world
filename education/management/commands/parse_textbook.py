"""PDF підручника → pipeline_out/<profile>/textbook.json (+ report.html). Тонка обгортка над run_pipeline.

    python manage.py parse_textbook --profile math_merzlyak_5 --pages 1-46 --workers 4
    python manage.py parse_textbook --profile math_tarasenkova_6 --pages 5-120 --vision-limit 10
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from education.pdf_pipeline.run import STAGES, PipelineError, default_engine, run_pipeline


class Command(BaseCommand):
    help = "Розпізнає PDF підручника і пише textbook.json + report.html (див. docs/pdf_pipeline)"
    engine_factory = staticmethod(default_engine)          # тести підміняють на Fake OCR

    def add_arguments(self, parser):
        parser.add_argument("--profile", required=True, help="math_merzlyak_5 | math_tarasenkova_6")
        parser.add_argument("--pdf", help="шлях до PDF (за замовчуванням — pdf_name з профілю)")
        parser.add_argument("--pages", help='"5-46" або "5-20,287-299"; за замовчуванням — усі')
        parser.add_argument("--out", default="pipeline_out")
        parser.add_argument("--from-stage", choices=STAGES)
        parser.add_argument("--to-stage", choices=STAGES)
        parser.add_argument("--force", action="store_true", help="усе без кешу")
        parser.add_argument("--workers", type=int, default=1)
        parser.add_argument("--vision-limit", type=int, default=0)
        parser.add_argument("--vision-dry-run", action="store_true")
        parser.add_argument("--no-report", action="store_true")
        parser.add_argument("--first-exercise", type=int, default=1,
                            help="номер першої вправи на цих сторінках (якщо --pages починається не з початку книги)")
        parser.add_argument("--ocr-engine", choices=["tesseract", "pdftext"],
                            help="pdftext — вбудований текстовий шар PDF (за замовчуванням — з профілю)")

    def handle(self, *args, **opts):
        from education.pdf_pipeline.config import PipelineConfig
        from education.pdf_pipeline.ingest.images import parse_page_range
        from education.pdf_pipeline.ingest.pdf_inspect import open_pdf
        from education.pdf_pipeline.profiles import get_profile

        try:
            profile = get_profile(opts["profile"])
        except KeyError as exc:
            raise CommandError(str(exc)) from exc
        pdf = Path(opts["pdf"] or profile.pdf_name)
        if not pdf.is_file():
            raise CommandError(f"PDF не знайдено: {pdf}")
        if opts["pages"]:
            pages = parse_page_range(opts["pages"])
        else:
            with open_pdf(pdf) as doc:
                pages = list(range(1, doc.page_count + 1))

        try:
            res = run_pipeline(pdf, profile.code, pages, PipelineConfig.from_env_file(), out_dir=opts["out"],
                               from_stage=opts["from_stage"], to_stage=opts["to_stage"], force=opts["force"],
                               workers=opts["workers"], engine_factory=self.engine_factory,
                               vision_limit=opts["vision_limit"], vision_dry_run=opts["vision_dry_run"],
                               report=not opts["no_report"], ocr_engine=opts["ocr_engine"],
                               first_exercise=opts["first_exercise"])
        except PipelineError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write("Етапи: " + ", ".join(f"{k} {v:.1f} с" for k, v in res.timings.items()))
        if res.failed_pages:
            self.stdout.write(self.style.WARNING(f"Сторінки з помилками: {dict(sorted(res.failed_pages.items()))}"))
        stats = res.counts.get("export")
        if stats:
            self.stdout.write(f"Вправ: {stats['exercises']}, підпунктів: {stats['subexercises']}, "
                              f"рисунків: {stats['figures']}, на перевірку: {stats['needs_review']}")
        for name in ("textbook.json", "report.html", "run_manifest.json"):
            path = res.out_dir / name
            if path.exists():
                self.stdout.write(self.style.SUCCESS(f"  {path}"))
        if res.textbook_path:
            self.stdout.write(f"Далі: python manage.py import_textbook --json {res.textbook_path} --dry-run")
