"""Vision-LLM корекція (фаза 15): дорогий, але точний прохід лише для проблемних зон.

Ідея: Tesseract читає все безкоштовно, валідація (фаза 14) показує, де він помилився.
Тільки ці вправи ми вирізаємо з картинки сторінки і відправляємо в vision-модель разом
з OCR-текстом як підказкою. Відповідь — строгий JSON, і ми **не довіряємо їй сліпо**
(деталі перевірки — у ``vision_response.judge``).

Модуль не імпортує Django, а ``google-genai`` імпортується лише при створенні Gemini-клієнта.

BE-S12: файл був 571 рядок і змішував кілька шарів. Тепер тут лишається прогін
(``run_vision``) і CLI (``main``) — решта розведена по модулях нижче, а цей файл
реекспортує їхні публічні імена, щоб усі існуючі імпорти не зламалися:

- ``vision_prompts.py``   — промпт, схема відповіді, перевірка проти схеми;
- ``vision_client.py``    — клієнт, кеш на диску, денний бюджет, ретраї з backoff;
- ``vision_targets.py``   — які вправи показати моделі і підготовка картинки;
- ``vision_response.py``  — суддя (приймати/відкидати відповідь) і застосування.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .datatypes import Node
from .vision_client import (
    CachedClient,
    DailyBudget,
    DEFAULT_DAILY_BUDGET,
    FakeVisionClient,
    GeminiVisionClient,
    VisionBudgetExceeded,
    VisionClient,
    VisionError,
    cache_key,
    call_with_backoff,
    make_client,
    vision_env,
)
from .vision_prompts import PROMPT_V1, PROMPT_VERSION, PROMPTS, RESPONSE_SCHEMA, validate_response
from .vision_response import (
    MAX_AUTO_CER,
    MAX_LENGTH_RATIO,
    MIN_LENGTH_BASE,
    Decision,
    _canon_apostrophes,
    apply_response,
    judge,
    vision_full_text,
)
from .vision_targets import (
    CROP_PAD,
    LOW_CONF,
    TOKENS_PER_TILE,
    VisionTarget,
    _written_subitems,
    crop_png,
    estimate_tokens,
    exercise_ocr_text,
    select_targets,
)

MAX_CONSECUTIVE_ERRORS = 5    # стільки помилок поспіль → зупиняємо прогін (квота / немає мережі), а не чекаємо на кожну зону

__all__ = [
    "PROMPT_VERSION", "DEFAULT_DAILY_BUDGET", "MAX_CONSECUTIVE_ERRORS", "MAX_LENGTH_RATIO", "MAX_AUTO_CER",
    "MIN_LENGTH_BASE", "LOW_CONF", "CROP_PAD", "TOKENS_PER_TILE", "RESPONSE_SCHEMA", "PROMPT_V1", "PROMPTS",
    "VisionError", "VisionBudgetExceeded", "VisionClient", "call_with_backoff", "DailyBudget", "cache_key",
    "CachedClient", "GeminiVisionClient", "FakeVisionClient", "VisionTarget", "exercise_ocr_text", "select_targets",
    "crop_png", "estimate_tokens", "validate_response", "vision_full_text", "Decision", "judge", "apply_response",
    "VisionStats", "run_vision", "vision_env", "make_client", "main",
]


# --------------------------------------------------------------------------- прогін


@dataclass
class VisionStats:
    candidates: int = 0
    selected: int = 0
    sent: int = 0
    cached: int = 0
    estimated_tokens: int = 0
    budget_stopped: bool = False
    aborted: bool = False          # MAX_CONSECUTIVE_ERRORS помилок поспіль
    errors: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    planned: list[dict[str, Any]] = field(default_factory=list)


def run_vision(root: Node, page_images: Mapping[int, Path | np.ndarray], client: VisionClient | None,
               layouts: Iterable[Any] = (), limit: int | None = None, dry_run: bool = False,
               prompt_version: str = PROMPT_VERSION, natural_numbers: bool = True) -> VisionStats:
    """Відправляє вибрані зони в модель і застосовує відповіді з перевірками.

    dry_run — нічого не відправляє, лише показує список зон і оцінку токенів.
    Бюджет вичерпано посеред прогону → зупиняємось, решта вправ лишається як була.
    """

    template = PROMPTS[prompt_version]
    targets = select_targets(root, layouts)
    stats = VisionStats(candidates=len(targets))
    if limit is not None:
        targets = targets[:limit]
    stats.selected = len(targets)
    from .preprocess import PageImageCache
    arrays = {p: v for p, v in page_images.items() if isinstance(v, np.ndarray)}     # готові картинки (тести)
    images = PageImageCache({p: v for p, v in page_images.items() if p not in arrays})
    streak = 0
    for target in targets:
        src = target.source
        page_img = arrays.get(src.pdf_page)
        if page_img is None:
            page_img = images.get(src.pdf_page)
        if page_img is None:
            continue
        png = crop_png(page_img, src.bbox)
        stats.estimated_tokens += estimate_tokens(src.bbox.width + 2 * CROP_PAD, src.bbox.height + 2 * CROP_PAD)
        ocr_text = exercise_ocr_text(target.exercise)
        stats.planned.append({"exercise": target.exercise.number, "page": src.pdf_page,
                              "reasons": target.reasons, "bytes": len(png)})
        if dry_run or client is None:
            continue
        try:
            response = client.transcribe(png, template.format(ocr=ocr_text), RESPONSE_SCHEMA)
        except VisionBudgetExceeded:
            stats.budget_stopped = True
            break
        except Exception as exc:  # noqa: BLE001 — одна зона з помилкою не валить прогін
            stats.errors += 1
            streak += 1
            target.exercise.data["vision_status"] = "error"
            target.exercise.data["vision_reason"] = str(exc)[:200]
            if streak >= MAX_CONSECUTIVE_ERRORS:
                stats.aborted = True
                break
            continue
        streak = 0
        if getattr(client, "last_from_cache", False):
            stats.cached += 1
        else:
            stats.sent += 1
        labels = [s.number for s in _written_subitems(target.exercise)]
        decision = judge(ocr_text, response, labels)
        apply_response(target.exercise, response, decision, natural_numbers)
        stats.by_status[decision.status] = stats.by_status.get(decision.status, 0) + 1
    return stats


# --------------------------------------------------------------------------- CLI


def main(argv: Sequence[str] | None = None) -> int:
    """python -m education.pdf_pipeline.vision --tree pipeline_out/m5_tree.json --pdf <pdf> --limit 3 [--dry-run]"""
    from .config import PipelineConfig, read_env_file
    from .images import get_page_images

    parser = argparse.ArgumentParser(description="Vision-LLM корекція проблемних вправ дерева")
    parser.add_argument("--tree", required=True, type=Path)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--out", type=Path, help="куди записати оновлене дерево (за замовчуванням <tree>_vision.json)")
    parser.add_argument("--limit", type=int, default=3, help="скільки зон відправити (за замовчуванням 3)")
    parser.add_argument("--dry-run", action="store_true", help="нічого не відправляти, показати план і токени")
    parser.add_argument("--budget", type=int, default=DEFAULT_DAILY_BUDGET)
    parser.add_argument("--fractions", action="store_true", help="дробові відповіді нормальні (6 клас)")
    args = parser.parse_args(argv)

    env = {**read_env_file(), **os.environ}
    cfg = PipelineConfig.from_env(env)
    root = Node.from_dict(json.loads(args.tree.read_text(encoding="utf-8")))
    pages = sorted({t.source.pdf_page for t in select_targets(root)})
    page_images = {p.pdf_page: p.path for p in get_page_images(args.pdf, pages, cfg)} if pages else {}
    client = None if args.dry_run else make_client(cfg.cache_dir, args.budget, env)
    stats = run_vision(root, page_images, client, limit=args.limit, dry_run=args.dry_run,
                       natural_numbers=not args.fractions)

    for item in stats.planned:
        print(f"  №{item['exercise']:>5}  стор. {item['page']:>3}  {','.join(item['reasons']):<30} {item['bytes'] // 1024} КБ")
    print(f"Кандидатів: {stats.candidates}, вибрано: {stats.selected}, ~{stats.estimated_tokens} токенів картинок")
    if args.dry_run:
        return 0
    print(f"Відправлено: {stats.sent}, з кешу: {stats.cached}, помилок: {stats.errors}, "
          f"бюджет зупинив: {stats.budget_stopped}, статуси: {stats.by_status}")
    if client is not None:
        print(f"Використано сьогодні: {client.budget.used}/{client.budget.limit}")
    out = args.out or args.tree.with_name(args.tree.stem + "_vision.json")
    out.write_text(json.dumps(root.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Дерево: {out}")
    for ex in root.find("exercise"):
        if "vision_status" in ex.data:
            print(f"\n№{ex.number} [{ex.data['vision_status']}] {ex.data.get('vision_reason', '')}")
            print("  OCR:   ", ex.data.get("ocr_text", "").replace("\n", " | ")[:300])
            print("  Vision:", ex.data.get("vision_text", "").replace("\n", " | ")[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
