"""Оркестрація етапів (фаза 17): inspect → images → preprocess → ocr → layout →
structure → vision → validate → export.

Винесено з ``run.py`` (BE-S12): це сам «мотор» прогону — ``run_pipeline`` і
допоміжні кроки (``_run_ocr``, ``_run_structure``). CLI — у ``cli.py``,
запис ``run_manifest.json`` — у ``manifest.py``.

- **images / preprocess / ocr** мають кеш на диску: повторний прогін бере все з кешу.
- ``--from-stage X`` — етапи від X **перераховуються без кешу** (раніші — з кешу);
  ``--to-stage Y`` — зупинитися після Y. ``--force`` = ``--from-stage images``.
- ``vision`` вмикається лише ``--vision-limit N`` (або ``--vision-dry-run``): він платний.
- Валідація йде **після** vision, щоб звіт показував уже виправлений стан.
- Помилка на одній сторінці не валить прогін: сторінка пропускається, а в ``problems``
  з'являється ``page_failed`` (error).
"""
from __future__ import annotations

import functools
import logging
import time
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import PipelineConfig
from ..datatypes import Node, PageImage, PageOcr, SourceRef
from ..ingest.preprocess import PreparedPage
from ..ocr.base import OcrEngine, OcrParams
from ..output.validate import Problem
from .manifest import _write_manifest

log = logging.getLogger("pdf_pipeline")

STAGES = ("inspect", "images", "preprocess", "ocr", "layout", "structure", "vision", "validate", "export")
CACHED_STAGES = ("images", "preprocess", "ocr")

EngineFactory = Callable[[PipelineConfig], OcrEngine]


def pdftext_engine(pdf_path: Path, cfg: PipelineConfig) -> OcrEngine:
    from ..ocr.pdftext import PdfTextEngine
    return PdfTextEngine(pdf_path)


def default_engine(cfg: PipelineConfig) -> OcrEngine:
    from ..ocr.tesseract import TesseractEngine
    return TesseractEngine(cfg)


class PipelineError(RuntimeError):
    """Прогін не має сенсу продовжувати (напр. OCR не працює на жодній сторінці)."""


# --------------------------------------------------------------------------- паралельний OCR

_WORKER_ENGINE: OcrEngine | None = None


def _ocr_worker(prepared: dict[str, Any], cfg: PipelineConfig, params: OcrParams, force: bool,
                factory: EngineFactory) -> dict[str, Any]:
    """Виконується в окремому процесі: рушій створюється один раз на процес."""
    global _WORKER_ENGINE
    from ..ocr import ocr_page
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


def _page_problem(page: int, stage: str, exc: BaseException) -> Problem:
    return Problem("page_failed", "error", f"{stage}: {type(exc).__name__}: {exc}"[:300],
                   SourceRef(page), f"стор. {page}", data={"stage": stage})


# --------------------------------------------------------------------------- головна функція


def run_pipeline(pdf_path: str | Path, profile_code: str, pages: Iterable[int], cfg: PipelineConfig, *,
                 out_dir: str | Path = "pipeline_out", from_stage: str | None = None, to_stage: str | None = None,
                 force: bool = False, workers: int = 1, engine_factory: EngineFactory = default_engine,
                 ocr_params: OcrParams | None = None, vision_limit: int = 0, vision_dry_run: bool = False,
                 vision_client: Any = None, report: bool = True, ocr_engine: str | None = None,
                 first_exercise: int = 1) -> RunResult:
    from ..profiles import get_profile

    pdf_path = Path(pdf_path)
    profile = get_profile(profile_code)
    if engine_factory is default_engine and (ocr_engine or profile.ocr_engine) == "pdftext":
        engine_factory = functools.partial(pdftext_engine, pdf_path)
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
        from ..ingest.pdf_inspect import LOW_RES_PPI, classify_pdf, inspect_page, open_pdf, pdf_sha256
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
            from ..ingest.images import _get_page_image
            from ..ingest.pdf_inspect import open_pdf
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
            from ..ingest.preprocess import preprocess_page
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
            from ..content.normalize import normalize_lines
            from ..layout import analyze_document
            ocr_results = [state["ocr"][p] for p in alive(state["ocr"])]
            layouts, headers = analyze_document(ocr_results)
            if profile.book_page_offset is not None:
                for lay in layouts:
                    lay.book_page = lay.pdf_page + profile.book_page_offset
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
            _run_structure(profile, res, state, overwrite_figures=forced("structure"), first_exercise=first_exercise)

    if enabled("vision") and (vision_limit > 0 or vision_dry_run):
        with stage("vision"):
            from ..vision import make_client, run_vision
            client = vision_client
            if client is None and not vision_dry_run:
                client = make_client(cfg.cache_dir)
            vstats = run_vision(res.root, state["page_paths"], client, layouts=res.layouts,
                                limit=vision_limit or None, dry_run=vision_dry_run,
                                natural_numbers=state["natural_numbers"])
            res.counts["vision"] = {"candidates": vstats.candidates, "selected": vstats.selected,
                                    "sent": vstats.sent, "cached": vstats.cached, "errors": vstats.errors,
                                    "budget_stopped": vstats.budget_stopped, "aborted": vstats.aborted,
                                    "by_status": vstats.by_status,
                                    "estimated_tokens": vstats.estimated_tokens, "dry_run": vision_dry_run}

    if enabled("validate"):
        with stage("validate"):
            from ..output.validate import count_by_code, tree_stats, validate
            skip = set(profile.skip_pages) | state.get("answer_pages", set())
            res.problems += validate(res.root, res.layouts, state["parse_issues"],
                                     answer_numbers=state.get("answer_numbers", ()),
                                     figure_ids=state.get("figure_ids", ()), skip_pages=skip)
            res.problems.sort(key=Problem.sort_key)
            res.counts["problems"] = count_by_code(res.problems)
            if report:
                from ..output.report import write_report
                debug = sorted((Path(out_dir) / "layout_debug").glob("*.png"))
                write_report(res.out_dir / "report.html", res.root, res.problems, tree_stats(res.root),
                             page_images=state["page_paths"], norm_stats=state.get("norm"), debug_pngs=debug)

    if enabled("export"):
        with stage("export"):
            from ..output.export import export_textbook, write_textbook
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
    from ..ocr import ocr_cache_path, ocr_page

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


def _run_structure(profile: Any, res: RunResult, state: dict[str, Any], overwrite_figures: bool = False,
                   first_exercise: int = 1) -> None:
    from ..content.answers import answer_lines_from_layouts, attach_answers, parse_answer_lines, summarize
    from ..content.exercises import enrich_exercises, flag_difficulty_order
    from ..content.figures import attach_figures, extract_all_figures
    from ..content.math_text import detect_fraction_bars, enrich_math
    from ..ingest.preprocess import load_image
    from ..structure import parse_structure

    page_paths = {p: img.path for p, img in state["images"].items() if p not in res.failed_pages}
    state["page_paths"] = page_paths
    answer_pages: set[int] = set()
    if profile.answers_pages:
        first, last = profile.answers_pages
        answer_pages = set(range(first, last + 1))
    state["answer_pages"] = answer_pages
    skip = set(profile.skip_pages) | answer_pages
    body = [lay for lay in res.layouts if lay.pdf_page not in skip]

    parsed = parse_structure(profile, body, first_exercise=first_exercise)
    root = parsed.root
    state["parse_issues"] = parsed.issues
    engines = {o.engine for o in state.get("ocr", {}).values()}
    trusted_text = bool(engines) and all(e.startswith("pdftext") for e in engines)
    enrich = enrich_exercises(root, res.layouts, profile, page_paths, trusted_text=trusted_text)
    flag_difficulty_order(root)

    bars = {}
    for lay in body:
        if lay.pdf_page in page_paths:
            found = detect_fraction_bars(load_image(page_paths[lay.pdf_page]))
            if found:
                bars[lay.pdf_page] = found
    natural = profile.grade <= 5
    state["natural_numbers"] = natural
    math = enrich_math(root, natural_numbers=natural, fraction_bars=bars,
                      trusted_text=trusted_text)

    figures = extract_all_figures(body, page_paths, res.out_dir / "figures", overwrite=overwrite_figures,
                                   strict=profile.strict_figures)
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
