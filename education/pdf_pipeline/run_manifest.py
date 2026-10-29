"""Запис ``run_manifest.json`` (фаза 17): підсумок прогону — версії, час, параметри, лічильники.

Винесено з ``run.py`` (BE-S12): це самостійний крок *після* того, як прогін уже
відбувся — бере готовий ``RunResult`` і серіалізує його. Оркестрація етапів — у
``run_orchestrator.py``, CLI — у ``run_cli.py``.
"""
from __future__ import annotations

import subprocess
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from . import __version__
from .cache import save_json
from .ocr.base import OcrParams
from .schema import SCHEMA_VERSION

if TYPE_CHECKING:
    from .run_orchestrator import RunResult


def git_commit(cwd: Path | None = None) -> str | None:
    try:
        out = subprocess.run(["git", "--no-optional-locks", "rev-parse", "--short", "HEAD"], cwd=cwd,
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def _write_manifest(res: RunResult, pdf_path: Path, sha: str | None, started_at: str, params: OcrParams,
                    workers: int, from_stage: str | None, to_stage: str | None,
                    vision_limit: int, vision_dry_run: bool) -> Path:
    manifest = {
        "pipeline_version": __version__, "schema_version": SCHEMA_VERSION, "git_commit": git_commit(),
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "pdf": {"name": pdf_path.name, "sha256": sha},
        "params": {"profile": res.profile, "pages": _compact_pages(res.pages), "workers": workers,
                   "from_stage": from_stage, "to_stage": to_stage, "ocr": params.to_dict(),
                   "vision_limit": vision_limit, "vision_dry_run": vision_dry_run},
        "stages": res.stages_run,
        "timings_s": res.timings,
        "total_s": round(sum(res.timings.values()), 2),
        "failed_pages": {str(k): v for k, v in sorted(res.failed_pages.items())},
        "counts": res.counts,
        "outputs": {"textbook": res.textbook_path.as_posix() if res.textbook_path else None,
                    "report": (res.out_dir / "report.html").as_posix() if "validate" in res.stages_run else None},
    }
    return save_json(res.out_dir / "run_manifest.json", manifest)


def _compact_pages(pages: Sequence[int]) -> str:
    """[5, 6, 7, 9] → "5-7,9"."""
    parts, start, prev = [], None, None
    for p in pages:
        if start is None:
            start = prev = p
        elif p == prev + 1:
            prev = p
        else:
            parts.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = p
    if start is not None:
        parts.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(parts)
