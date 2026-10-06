"""Спільні дрібниці для кешу на диску: атомарний запис JSON і короткі хеш-ключі."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def save_json(path: str | Path, data: Any) -> Path:
    """Записує JSON **атомарно**: спершу в тимчасовий файл поруч, потім перейменування.

    Якщо програму перервати посеред запису (Ctrl+C, вимкнули світло), на диску
    лишиться або старий файл, або новий — але ніколи не обрізаний наполовину,
    який потім зламав би читання кешу.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)          # атомарна заміна (і в Windows, і в Linux)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def short_hash(*parts: Any, length: int = 12) -> str:
    """Короткий стабільний хеш від будь-яких JSON-сумісних частин (для імен папок кешу)."""
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:length]
