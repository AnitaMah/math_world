"""Налаштування PDF-пайплайна. Без Django."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CACHE_DIR = Path("pipeline_cache")

ENV_TESSERACT_CMD = "TESSERACT_CMD"
ENV_TESSDATA_DIR = "TESSDATA_PREFIX_BEST"
ENV_CACHE_DIR = "PIPELINE_CACHE_DIR"


def _get(environ: Mapping[str, str], name: str) -> str | None:
    """Повертає значення змінної без пробілів по краях або None, якщо її немає чи вона порожня."""
    value = environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


@dataclass(frozen=True)
class PipelineConfig:
    """Налаштування пайплайна: де Tesseract, де моделі мов і куди складати кеш.

    Об'єкт незмінний (frozen): створюється один раз на початку прогону
    і передається в усі етапи. Зазвичай створюється через ``from_env()``.
    """

    tesseract_cmd: str | None
    tessdata_dir: Path | None
    cache_dir: Path

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> PipelineConfig:
        """Збирає налаштування зі змінних середовища.

        Читає ``TESSERACT_CMD``, ``TESSDATA_PREFIX_BEST``, ``PIPELINE_CACHE_DIR``.
        Відсутні або порожні змінні: ``tesseract_cmd`` і ``tessdata_dir`` → None,
        ``cache_dir`` → ``pipeline_cache``.

        :param environ: звідки читати; за замовчуванням ``os.environ``.
            У тестах передаємо звичайний dict.
        """
        if environ is None:
            environ = os.environ

        tesseract_cmd = _get(environ, ENV_TESSERACT_CMD)

        tessdata_raw = _get(environ, ENV_TESSDATA_DIR)
        tessdata_dir = Path(tessdata_raw) if tessdata_raw else None

        cache_raw = _get(environ, ENV_CACHE_DIR)
        cache_dir = Path(cache_raw) if cache_raw else DEFAULT_CACHE_DIR

        return cls(
            tesseract_cmd=tesseract_cmd,
            tessdata_dir=tessdata_dir,
            cache_dir=cache_dir,
        )
