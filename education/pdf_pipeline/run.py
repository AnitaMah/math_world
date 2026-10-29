"""Оркестратор (фаза 17): одна команда від PDF до ``textbook.json``.

    python -m education.pdf_pipeline.run --pdf 5-klas-matematika-merzljak-2018-1-46.pdf \\
        --profile math_merzlyak_5 --pages 5-46 --workers 4

Результат у ``<out>/<profile>/``: ``textbook.json``, ``report.html``, ``run_manifest.json``, ``figures/``.

BE-S12: файл був 496 рядків і змішував розбір аргументів командного рядка з
оркестрацією етапів. Тепер тут лише тонкий реекспорт, щоб усі існуючі
``from .run import ...`` / ``from education.pdf_pipeline.run import ...`` продовжували
працювати без змін:

- ``run_orchestrator.py`` — самі етапи прогону (``run_pipeline`` і допоміжні);
- ``run_manifest.py``     — запис ``run_manifest.json``;
- ``run_cli.py``          — розбір аргументів командного рядка (``main``).
"""
from __future__ import annotations

import sys

from .run_cli import main
from .run_manifest import _compact_pages, _write_manifest, git_commit
from .run_orchestrator import (
    CACHED_STAGES,
    STAGES,
    EngineFactory,
    PipelineError,
    RunResult,
    _ocr_worker,
    _page_problem,
    _run_ocr,
    _run_structure,
    _stage_range,
    default_engine,
    log,
    pdftext_engine,
    run_pipeline,
)

__all__ = [
    "STAGES", "CACHED_STAGES", "EngineFactory", "pdftext_engine", "default_engine", "PipelineError",
    "RunResult", "run_pipeline", "git_commit", "main", "_stage_range", "_compact_pages", "_write_manifest",
    "_page_problem", "_run_ocr", "_run_structure", "_ocr_worker", "log",
]

if __name__ == "__main__":
    sys.exit(main())
