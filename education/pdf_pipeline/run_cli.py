"""CLI для оркестратора (фаза 17)::

    python -m education.pdf_pipeline.run --pdf 5-klas-matematika-merzljak-2018-1-46.pdf \\
        --profile math_merzlyak_5 --pages 5-46 --workers 4

Винесено з ``run.py`` (BE-S12): лише розбір аргументів командного рядка і друк
підсумку. Сама оркестрація етапів — у ``run_orchestrator.py``.
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from .config import PipelineConfig
from .run_orchestrator import STAGES, PipelineError, run_pipeline

log = logging.getLogger("pdf_pipeline")


def main(argv: Sequence[str] | None = None) -> int:
    from .images import parse_page_range
    from .pdf_inspect import open_pdf

    parser = argparse.ArgumentParser(description="PDF підручника → textbook.json (+ report.html)")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--profile", required=True, help="math_merzlyak_5 | math_tarasenkova_6")
    parser.add_argument("--pages", help='напр. "5-46" або "5-20,287-299"; за замовчуванням — усі')
    parser.add_argument("--out", type=Path, default=Path("pipeline_out"))
    parser.add_argument("--from-stage", choices=STAGES, help="з цього етапу — перерахувати без кешу")
    parser.add_argument("--to-stage", choices=STAGES, help="зупинитися після цього етапу")
    parser.add_argument("--force", action="store_true", help="усе без кешу (= --from-stage images)")
    parser.add_argument("--workers", type=int, default=1, help="процесів для OCR")
    parser.add_argument("--vision-limit", type=int, default=0, help="скільки вправ віддати vision-LLM (0 — вимкнено)")
    parser.add_argument("--vision-dry-run", action="store_true", help="показати, що піде у vision, без запитів")
    parser.add_argument("--no-report", action="store_true")
    parser.add_argument("--ocr-engine", choices=["tesseract", "pdftext"], help="за замовчуванням — з профілю")
    parser.add_argument("--first-exercise", type=int, default=1,
                        help="номер першої вправи на цих сторінках (якщо --pages починається не з початку книги)")
    parser.add_argument("-v", "--verbose", action="count", default=0, help="-v — по сторінках, -vv — debug")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose >= 2 else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    if args.verbose == 0:      # етапи і час видно завжди, прогрес по сторінках — лише з -v
        log.addFilter(lambda r: "сторінка" not in r.getMessage() or r.levelno > logging.INFO)

    cfg = PipelineConfig.from_env_file()
    if args.pages:
        pages = parse_page_range(args.pages)
    else:
        with open_pdf(args.pdf) as doc:
            pages = list(range(1, doc.page_count + 1))
    try:
        res = run_pipeline(args.pdf, args.profile, pages, cfg, out_dir=args.out, from_stage=args.from_stage,
                           to_stage=args.to_stage, force=args.force, workers=args.workers,
                           vision_limit=args.vision_limit, vision_dry_run=args.vision_dry_run,
                           report=not args.no_report, ocr_engine=args.ocr_engine,
                           first_exercise=args.first_exercise)
    except PipelineError as exc:
        print(f"\nПОМИЛКА: {exc}", file=sys.stderr)
        return 2

    print(f"\nГотово за {sum(res.timings.values()):.1f} с: " + ", ".join(f"{k} {v:.1f}" for k, v in res.timings.items()))
    if res.failed_pages:
        print(f"Сторінки з помилками: {res.failed_pages}")
    if "export" in res.counts:
        s = res.counts["export"]
        print(f"Вправ: {s['exercises']}, підпунктів: {s['subexercises']}, рисунків: {s['figures']}, "
              f"на перевірку: {s['needs_review']}")
    if res.problems:
        sev = Counter(p.severity for p in res.problems)
        print(f"Проблем: {len(res.problems)} ({dict(sev)})")
    for name in ("textbook.json", "report.html", "run_manifest.json"):
        if (res.out_dir / name).exists():
            print(f"  {res.out_dir / name}")
    return 1 if res.failed_pages and len(res.failed_pages) == len(res.pages) else 0
