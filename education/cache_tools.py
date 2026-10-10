"""Розмір і очищення pipeline_cache/ (план 0872).

pipeline_cache/<sha256 PDF>/{pages,prep,ocr}: pages — рендер сторінок, prep — оброблені для OCR (відновлюється з pages),
ocr — результат розпізнавання (дорогий). pipeline_cache/vision/ — відповіді Gemini і бюджет: цією командою не чіпається.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

PARTS = ("pages", "prep", "ocr")
DEFAULT_PARTS = ("prep",)          # безпечне: відновлюється автоматично при наступному прогоні


@dataclass
class CacheEntry:
    sha: str
    path: Path
    label: str                     # profile_code з БД або «(немає в БД)»
    known: bool
    sizes: dict = field(default_factory=dict)   # частина -> байти

    @property
    def total(self) -> int:
        return sum(self.sizes.values())


def dir_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def human(n: int) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024


def scan(cache_dir: Path, known_shas: dict[str, str]) -> list[CacheEntry]:
    """Кеші PDF (теки з sha) із розмірами частин. known_shas: sha → profile_code із БД."""
    entries = []
    if not cache_dir.is_dir():
        return entries
    for d in sorted(p for p in cache_dir.iterdir() if p.is_dir() and any((p / part).is_dir() for part in PARTS)):
        entries.append(CacheEntry(
            sha=d.name, path=d, label=known_shas.get(d.name, "(немає в БД)"), known=d.name in known_shas,
            sizes={part: dir_size(d / part) for part in PARTS}))
    return entries


def other_size(cache_dir: Path, entries: list[CacheEntry]) -> int:
    """Усе, що не є кешем PDF (vision/, бюджети) — для підсумку."""
    return dir_size(cache_dir) - sum(e.total for e in entries)


def clear(entries: list[CacheEntry], parts: tuple[str, ...], include_unknown: bool = False) -> int:
    """Видаляє вказані частини; повертає звільнені байти. Кеші, яких немає в БД, — лише з include_unknown."""
    freed = 0
    for e in entries:
        if not e.known and not include_unknown:
            continue
        for part in parts:
            target = e.path / part
            if target.is_dir():
                freed += e.sizes.get(part, 0)
                shutil.rmtree(target)
    return freed
