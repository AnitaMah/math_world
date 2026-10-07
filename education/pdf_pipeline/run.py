"""Оркестратор (фаза 17): одна команда від PDF до ``textbook.json``.

    python -m education.pdf_pipeline.run --pdf 5-klas-matematika-merzljak-2018-1-46.pdf \\
        --profile math_merzlyak_5 --pages 5-46 --workers 4

Етапи (по порядку)::

    inspect → images → preprocess → ocr → layout → structure → vision → validate → export

- **images / preprocess / ocr** мають кеш на диску: повторний прогін бере все з кешу.
- ``--from-stage X`` — етапи від X **перераховуються без кешу** (раніші — з кешу);
  ``--to-stage Y`` — зупинитися після Y. ``--force`` = ``--from-stage images``.
- ``vision`` вмикається лише ``--vision-limit N`` (або ``--vision-dry-run``): він платний.
- Валідація йде **після** vision, щоб звіт показував уже виправлений стан.
- Помилка на одній сторінці не валить прогін: сторінка пропускається, а в ``problems``
  з'являється ``page_failed`` (error).

Результат у ``<out>/<profile>/``: ``textbook.json``, ``report.html``, ``run_manifest.json``, ``figures/``.
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .cache import save_json
from .config import PipelineConfig
from .datatypes import Node, PageImage, PageOcr, SourceRef
from .ocr.base import OcrEngine, OcrParams
from .preprocess import PreparedPage
from .schema import SCHEMA_VERSION
from .validate import Problem

log = logging.getLogger("pdf_pipeline")

STAGES = ("inspect", "images", "preprocess", "ocr", "layout", "structure", "vision", "validate", "export")
CACHED_STAGES = ("images", "preprocess", "ocr")

EngineFactory = Callable[[PipelineConfig], OcrEngine]


def default_engine(cfg: PipelineConfig) -> OcrEngine:
    from .ocr.tesseract import TesseractEngine
    return TesseractEngine(cfg)


class PipelineError(RuntimeError):
    """Прогін не має сенсу продовжувати (напр. OCR не працює на жодній сторінці)."""


# --------------------------------------------------------------------------- паралельний OCR

_WORKER_ENGINE: OcrEngine | None = None


def _ocr_worker(prepared: dict[str, Any], cfg: PipelineConfig, params: OcrParams, force: bool,
                factory: EngineFactory) -> dict[str, Any]:
    """Виконується в окремому процесі: рушій створюється один раз на процес."""
    global _WORKER_ENGINE
    from .ocr import ocr_page
    if _WORKER_ENGINE is None:
        _WORKER_ENGINE = factory(cfg)
    return ocr_page(PreparedPage.from_dict(prepared), _WORKER_ENGINE, params, force=force).to_dict()


# --------------------------------------------------------------------------- стан прогону


@dataclass
class RunResult:
    profile: str
    out_dir: Path
    pages: list[int]
    stages_run: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    counts: dict[str, Any] = field(default_factory=dict)
    failed_pages: dict[int, str] = field(default_factory=dict)
    problems: list[Problem] = field(default_factory=list)
    root: Node | None = None
    layouts: list[Any] = field(default_factory=list)
    textbook_path: Path | None = None
    manifest_path: Path | None = None


def _stage_range(from_stage: str | None, to_stage: str | None) -> tuple[int, int]:
    start = STAGES.index(from_stage) if from_stage else None
    end = STAGES.index(to_stage) if to_stage else len(STAGES) - 1
    if start is not None and start > end:
        raise ValueError(f"--from-stage {from_stage} іде після --to-stage {to_stage}")
    return (start if start is not None else len(STAGES)), end


def git_commit(cwd: Path | None = None) -> str | None:
    try:
        out = subprocess.run(["git", "--no-optional-locks", "rev-parse", "--short", "HEAD"], cwd=cwd,
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def _page_problem(page: int, stage: str, exc: BaseException) -> Problem:
    return Problem("page_failed", "error", f"{stage}: {type(exc).__name__}: {exc}"[:300],
                   SourceRef(page), f"стор. {page}", data={"stage": stage})


# --------------------------------------------------------------------------- головна функція


def run_pipeline(pdf_path: str | Path, profile_code: str, pages: Iterable[int], cfg: PipelineConfig, *,
                 out_dir: str | Path = "pipeline_out", from_stage: str | None = None, to_stage: str | None = None,
                 force: bool = False, workers: int = 1, engine_factory: EngineFactory = default_engine,
                 ocr_params: OcrParams | None = None, vision_limit: int = 0, vision_dry_run: bool = False,
                 vision_client: Any = None, report: bool = True) -> RunResult:
    from .profiles import get_profile

    pdf_path = Path(pdf_path)
    profile = get_profile(profile_code)
    if force and from_stage is None:
        from_stage = "images"
    force_from, last = _stage_range(from_stage, to_stage)
    params = ocr_params or OcrParams()
    requested = sorted(set(pages))
    res = RunResult(profile=profile.code, out_dir=Path(out_dir) / profile.code, pages=requested)
    res.out_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    state: dict[str, Any] = {}

    def enabled(stage: str) -> bool:
        return STAGES.index(stage) <= last

    def forced(stage: str) -> bool:
        return STAGES.index(stage) >= force_from

    @contextmanager
    def stage(name: str):
        log.info("▶ %s%s", name, " (без кешу)" if name in CACHED_STAGES and forced(name) else "")
        t0 = time.perf_counter()
        yield
        res.timings[name] = round(time.perf_counter() - t0, 2)
        res.stages_run.append(name)
        log.info("  %s: %.1f с", name, res.timings[name])

    def alive(items: dict[int, Any]) -> list[int]:
        return [p for p in requested if p in items and p not in res.failed_pages]

    # ---------------------------------------------------------------- inspect
    with stage("inspect"):
        from .pdf_inspect import LOW_RES_PPI, classify_pdf, inspect_page, open_pdf, pdf_sha256
        state["sha"] = pdf_sha256(pdf_path)
        inspected = []
        with open_pdf(pdf_path) as doc:
            page_count = doc.page_count
            for p in requested:
                if not 1 <= p <= page_count:
                    raise ValueError(f"Сторінки {p} немає (у PDF {page_count} сторінок)")
                try:
                    inspected.append(inspect_page(doc[p - 1], p))
                except Exception as exc:  # noqa: BLE001 — інспекція лише інформативна
                    log.warning("сторінка %d: inspect не вдався: %s", p, exc)
        ppis = sorted(x.max_ppi for x in inspected if x.max_ppi)
        res.counts["pdf"] = {"kind": classify_pdf(inspected).value if inspected else None, "page_count": page_count,
                             "median_ppi": ppis[len(ppis) // 2] if ppis else None,
                             "low_res_pages": sum(1 for x in inspected if x.max_ppi and x.max_ppi < LOW_RES_PPI)}
    if enabled("images"):
        # ------------------------------------------------------------ images
        with stage("images"):
            from .images import _get_page_image
            from .pdf_inspect import open_pdf
            images: dict[int, PageImage] = {}
            with open_pdf(pdf_path) as doc:
                for i, p in enumerate(requested, 1):
                    try:
                        images[p] = _get_page_image(doc, state["sha"], p, cfg, force=forced("images"))
                    except Exception as exc:  # noqa: BLE001
                        log.warning("сторінка %d: images впала: %s", p, exc)
                        res.failed_pages[p] = "images"
                        res.problems.append(_page_problem(p, "images", exc))
                    if i % 10 == 0 or i == len(requested):
                        log.info("  images: сторінка %d/%d", i, len(requested))
            state["images"] = images

    if enabled("preprocess"):
        with stage("preprocess"):
            from .preprocess import preprocess_page
            prepared: dict[int, PreparedPage] = {}
            todo = alive(state["images"])
            for i, p in enumerate(todo, 1):
                try:
                    prepared[p] = preprocess_page(state["images"][p], force=forced("preprocess"))
                except Exception as exc:  # noqa: BLE001
                    log.warning("сторінка %d: preprocess впав: %s", p, exc)
                    res.failed_pages[p] = "preprocess"
                    res.problems.append(_page_problem(p, "preprocess", exc))
                if i % 10 == 0 or i == len(todo):
                    log.info("  preprocess: сторінка %d/%d", i, len(todo))
            state["prepared"] = prepared

    if enabled("ocr"):
        with stage("ocr"):
            todo = alive(state["prepared"])
            state["ocr"] = _run_ocr(state["prepared"], todo, cfg, params,
                                    forced("ocr"), workers, engine_factory, res)
            if todo and not state["ocr"]:
                # Усі сторінки впали — це налаштування (моделі, шлях), а не погані сторінки.
                # Не пишемо порожній textbook.json поверх доброго.
                first = next(p for p in res.problems if p.code == "page_failed")
                raise PipelineError(f"OCR не вдався на жодній сторінці. Перша помилка: {first.message}")

    if enabled("layout"):
        with stage("layout"):
            from .layout import analyze_document
            from .normalize import normalize_lines
            ocr_results = [state["ocr"][p] for p in alive(state["ocr"])]
            layouts, headers = analyze_document(ocr_results)
            norm = Counter()
            for lay in layouts:
                lay.body_lines, counts = normalize_lines(lay.body_lines)
                norm.update(counts)
            res.layouts = layouts
            state["norm"] = dict(norm)
            res.counts["layout"] = {"pages": len(layouts), "running_headers": len(headers),
                                    "empty_pages": sum(1 for lay in layouts if not lay.body_lines)}

    if enabled("structure"):
        with stage("structure"):
            _run_structure(profile, res, state, overwrite_figures=forced("structure"))

    if enabled("vision") and (vision_limit > 0 or vision_dry_run):
        with stage("vision"):
            from .vision import make_client, run_vision
            client = vision_client
            if client is None and not vision_dry_run:
                client = make_client(cfg.cache_dir)
            vstats = run_vision(res.root, state["page_paths"], client, layouts=res.layouts,
                                limit=vision_limit or None, dry_run=vision_dry_run,
                                natural_numbers=state["natural_numbers"])
            res.counts["vision"] = {"candidates": vstats.candidates, "selected": vstats.selected,
                                    "sent": vstats.sent, "cached": vstats.cached, "errors": vstats.errors,
                                    "budget_stopped": vstats.budget_stopped, "by_status": vstats.by_status,
                                    "estimated_tokens": vstats.estimated_tokens, "dry_run": vision_dry_run}

    if enabled("validate"):
        with stage("validate"):
            from .validate import count_by_code, tree_stats, validate
            skip = set(profile.skip_pages) | state.get("answer_pages", set())
            res.problems += validate(res.root, res.layouts, state["parse_issues"],
                                     answer_numbers=state.get("answer_numbers", ()),
                                     figure_ids=state.get("figure_ids", ()), skip_pages=skip)
            res.problems.sort(key=Problem.sort_key)
            res.counts["problems"] = count_by_code(res.problems)
            if report:
                from .report import write_report
                debug = sorted((Path(out_dir) / "layout_debug").glob("*.png"))
                write_report(res.out_dir / "report.html", res.root, res.problems, tree_stats(res.root),
                             page_images=state["page_paths"], norm_stats=state.get("norm"), debug_pngs=debug)

    if enabled("export"):
        with stage("export"):
            from .export import export_textbook, write_textbook
            data = export_textbook(res.root, res.problems, pdf_name=pdf_path.name, pdf_sha256=state["sha"],
                                   pages=[lay.pdf_page for lay in res.layouts])
            res.textbook_path = write_textbook(data, out_dir)
            res.counts["export"] = data["stats"]

    res.manifest_path = _write_manifest(res, pdf_path, state.get("sha"), started_at, params, workers,
                                        from_stage, to_stage, vision_limit, vision_dry_run)
    return res


# --------------------------------------------------------------------------- етапи-помічники


def _run_ocr(prepared: dict[int, PreparedPage], todo: list[int], cfg: PipelineConfig, params: OcrParams,
             force: bool, workers: int, factory: EngineFactory, res: RunResult) -> dict[int, PageOcr]:
    from .ocr import ocr_cache_path, ocr_page

    results: dict[int, PageOcr] = {}
    done = 0
    if workers <= 1:
        engine = factory(cfg)
        for p in todo:
            try:
                cached = not force and ocr_cache_path(prepared[p], engine, params).exists()
                results[p] = ocr_page(prepared[p], engine, params, force=force)
                res.counts.setdefault("ocr", Counter())["cached" if cached else "recognized"] += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("сторінка %d: OCR впав: %s", p, exc)
                res.failed_pages[p] = "ocr"
                res.problems.append(_page_problem(p, "ocr", exc))
            done += 1
            log.info("  ocr: сторінка %d/%d (PDF %d)", done, len(todo), p)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_ocr_worker, prepared[p].to_dict(), cfg, params, force, factory): p for p in todo}
            for fut in as_completed(futures):
                p = futures[fut]
                try:
                    results[p] = PageOcr.from_dict(fut.result())
                except Exception as exc:  # noqa: BLE001
                    log.warning("сторінка %d: OCR впав: %s", p, exc)
                    res.failed_pages[p] = "ocr"
                    res.problems.append(_page_problem(p, "ocr", exc))
                done += 1
                log.info("  ocr: сторінка %d/%d (PDF %d)", done, len(todo), p)
    res.counts["ocr"] = dict(res.counts.get("ocr", {}))
    return results


def _run_structure(profile: Any, res: RunResult, state: dict[str, Any], overwrite_figures: bool = False) -> None:
    from .answers import answer_lines_from_layouts, attach_answers, parse_answer_lines, summarize
    from .exercises import enrich_exercises, flag_difficulty_order
    from .figures import attach_figures, extract_all_figures
    from .math_text import detect_fraction_bars, enrich_math
    from .preprocess import load_image
    from .structure import parse_structure

    page_paths = {p: img.path for p, img in state["images"].items() if p not in res.failed_pages}
    state["page_paths"] = page_paths
    answer_pages: set[int] = set()
    if profile.answers_pages:
        first, last = profile.answers_pages
        answer_pages = set(range(first, last + 1))
    state["answer_pages"] = answer_pages
    skip = set(profile.skip_pages) | answer_pages
    body = [lay for lay in res.layouts if lay.pdf_page not in skip]

    parsed = parse_structure(profile, body)
    root = parsed.root
    state["parse_issues"] = parsed.issues
    enrich = enrich_exercises(root, res.layouts, profile, page_paths)
    flag_difficulty_order(root)

    bars = {}
    for lay in body:
        if lay.pdf_page in page_paths:
            found = detect_fraction_bars(load_image(page_paths[lay.pdf_page]))
            if found:
                bars[lay.pdf_page] = found
    natural = profile.grade <= 5
    state["natural_numbers"] = natural
    math = enrich_math(root, natural_numbers=natural, fraction_bars=bars)

    figures = extract_all_figures(body, page_paths, res.out_dir / "figures", overwrite=overwrite_figures)
    fig_stats = attach_figures(root, figures)
    state["figure_ids"] = [f.figure_id for f in figures]

    answers: dict[str, Any] = {}
    present = [lay for lay in res.layouts if lay.pdf_page in answer_pages]
    if present:
        key = parse_answer_lines(answer_lines_from_layouts(present, profile.answers_pages))
        att = attach_answers(root, key)
        state["answer_numbers"] = list(key.entries)
        answers = {**summarize(key), "attached": att.exercises_with_answers, "verified": att.verified,
                   "mismatched": att.mismatched}

    res.root = root
    res.counts["structure"] = {
        "parse_issues": len(parsed.issues), "exercises": enrich.exercises, "subitems": enrich.subitems,
        "homework": enrich.homework, "expressions": math.expressions, "expr_ok": math.ok,
        "expr_suspect": math.suspect, "expr_malformed": math.malformed, "fraction_pages": len(bars),
        "figures": len(figures), "figures_linked": fig_stats.get("linked", 0), "answers": answers,
    }


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


# --------------------------------------------------------------------------- CLI


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
                           report=not args.no_report)
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


if __name__ == "__main__":
    sys.exit(main())
