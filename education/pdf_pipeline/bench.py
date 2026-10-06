"""Бенчмарк OCR: наскільки розпізнаний текст відрізняється від ручної транскрипції.

Метрика CER (character error rate) = відстань Левенштейна / довжина еталону.
0 — ідеально; 0.05 — 5 помилкових символів на кожні 100.

Запуск (з кореня проєкту):
    python -m education.pdf_pipeline.bench
    python -m education.pdf_pipeline.bench --configs default_psm6,default_psm4 --out docs/pdf_pipeline/BENCH.md
"""
from __future__ import annotations

import argparse
import re
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from rapidfuzz.distance import Levenshtein

from .cache import load_json
from .config import PipelineConfig
from .datatypes import PageOcr
from .images import get_page_image
from .ocr import OcrEngine, OcrParams, ocr_page, words_to_lines
from .preprocess import PRESETS, PreprocessSpec, preprocess_page

DEFAULT_MANIFEST = Path("education/tests_pipeline/fixtures/golden/golden.json")

# --------------------------------------------------------------------------- метрика

_TRANSLATE = str.maketrans({
    "’": "'", "ʼ": "'", "`": "'", "‘": "'",
    "—": "-", "–": "-", "−": "-", "‐": "-",
    "«": '"', "»": '"', "“": '"', "”": '"', "„": '"',
})
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\s*\n\s*(\w)")
_SPACES_RE = re.compile(r"\s+")


def normalize_for_cer(text: str) -> str:
    """Прибирає відмінності, які не є помилками розпізнавання.

    - різні апострофи / тире / лапки → один варіант;
    - перенос слова в кінці рядка (`натураль-\\nних`) → склеєне слово;
    - будь-які пробіли й переноси рядків → один пробіл.
    """
    text = text.translate(_TRANSLATE)
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", text)
    return _SPACES_RE.sub(" ", text).strip()


def cer(hypothesis: str, reference: str) -> float:
    """Character Error Rate розпізнаного тексту відносно еталону (після нормалізації)."""
    hyp, ref = normalize_for_cer(hypothesis), normalize_for_cer(reference)
    if not ref:
        return 0.0 if not hyp else 1.0
    return Levenshtein.distance(hyp, ref) / len(ref)


def page_text(result: PageOcr) -> str:
    """Текст сторінки з OCR: рядки згори вниз."""
    return "\n".join(line.text for line in words_to_lines(result.words, result.page.pdf_page))


# --------------------------------------------------------------------------- конфігурації


@dataclass(frozen=True)
class BenchConfig:
    name: str
    preset: PreprocessSpec
    params: OcrParams


CONFIGS: dict[str, BenchConfig] = {c.name: c for c in [
    BenchConfig("raw_psm6", PRESETS["raw"], OcrParams(psm=6)),
    BenchConfig("default_psm6", PRESETS["default"], OcrParams(psm=6)),
    BenchConfig("default_psm4", PRESETS["default"], OcrParams(psm=4)),
    BenchConfig("default_psm3", PRESETS["default"], OcrParams(psm=3)),
    BenchConfig("default_psm6_ukr", PRESETS["default"], OcrParams(lang="ukr", psm=6)),
    BenchConfig("lowres_psm6", PRESETS["lowres"], OcrParams(psm=6)),
]}


@dataclass(frozen=True)
class GoldenPage:
    name: str
    pdf: Path
    page: int
    text_path: Path

    @property
    def text(self) -> str:
        return self.text_path.read_text(encoding="utf-8")


def load_manifest(path: Path = DEFAULT_MANIFEST) -> list[GoldenPage]:
    """Список еталонних сторінок; шляхи у файлі — відносно кореня проєкту (поточної папки)."""
    return [GoldenPage(e["name"], Path(e["pdf"]), int(e["page"]), Path(e["text"])) for e in load_json(path)]


@dataclass(frozen=True)
class BenchRow:
    config: str
    golden: str
    cer: float
    words: int
    mean_conf: float
    seconds: float


def run_bench(goldens: Sequence[GoldenPage], configs: Sequence[BenchConfig],
              cfg: PipelineConfig, engine: OcrEngine) -> list[BenchRow]:
    rows: list[BenchRow] = []
    for conf in configs:
        for g in goldens:
            page = get_page_image(g.pdf, g.page, cfg)
            prepared = preprocess_page(page, conf.preset)
            result = ocr_page(prepared, engine, conf.params)
            confs = [w.conf for w in result.words]
            rows.append(BenchRow(
                config=conf.name, golden=g.name, cer=cer(page_text(result), g.text),
                words=len(result.words), mean_conf=statistics.fmean(confs) if confs else 0.0,
                seconds=result.duration_ms / 1000,
            ))
    return rows


def format_table(rows: Sequence[BenchRow], engine_name: str) -> str:
    """Markdown-таблиця + середній CER по кожній конфігурації (найкраща — перша)."""
    lines = [f"### {date.today().isoformat()} — {engine_name}", "",
             "| конфігурація | сторінка | CER | слів | сер. conf | сек |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r.config} | {r.golden} | {r.cer:.3f} | {r.words} | {r.mean_conf:.1f} | {r.seconds:.1f} |")
    by_config: dict[str, list[float]] = {}
    for r in rows:
        by_config.setdefault(r.config, []).append(r.cer)
    lines += ["", "| конфігурація | середній CER |", "|---|---|"]
    for name, values in sorted(by_config.items(), key=lambda kv: statistics.fmean(kv[1])):
        lines.append(f"| {name} | {statistics.fmean(values):.3f} |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    from .ocr.tesseract import TesseractEngine

    parser = argparse.ArgumentParser(description="Бенчмарк OCR на еталонних сторінках")
    parser.add_argument("--configs", default=",".join(CONFIGS), help=f"через кому; є: {', '.join(CONFIGS)}")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, help="дописати таблицю в цей .md файл")
    args = parser.parse_args(argv)

    unknown = [c for c in args.configs.split(",") if c not in CONFIGS]
    if unknown:
        parser.error(f"невідомі конфігурації: {unknown}")

    cfg = PipelineConfig.from_env()
    engine = TesseractEngine(cfg)
    rows = run_bench(load_manifest(args.manifest), [CONFIGS[c] for c in args.configs.split(",")], cfg, engine)
    table = format_table(rows, engine.name)
    print(table)
    if args.out:
        with args.out.open("a", encoding="utf-8") as fh:
            fh.write("\n" + table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
