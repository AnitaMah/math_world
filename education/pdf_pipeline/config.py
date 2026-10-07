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


def read_env_file(path: str | Path = ".env") -> dict[str, str]:
    """Читає файл .env (рядки ``КЛЮЧ=значення``) у словник. Немає файлу — порожній словник.

    Коментарі (#) і порожні рядки пропускаються, лапки навколо значення знімаються.
    Власний мінімальний парсер, щоб пайплайн не залежав від Django/decouple.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


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

    @classmethod
    def from_env_file(cls, path: str | Path = ".env") -> PipelineConfig:
        """Як from_env, але спершу читає .env; справжні змінні середовища мають пріоритет.

        Використовується в командах для терміналу (bench, layout_debug...), бо
        `python -m ...` сам .env не читає — без цього підхоплювалися б не ті моделі.
        """
        return cls.from_env({**read_env_file(path), **os.environ})
