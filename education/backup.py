"""Автобекап SQLite-бази перед імпортом (план 0876). Відкат — окремою командою (0877).

Копія робиться через sqlite3.Connection.backup(): консистентна, навіть якщо базу хтось читає.
Файли: <DB_BACKUP_DIR>/db_YYYYMMDD_HHMMSS.sqlite3; лишається DB_BACKUP_KEEP найновіших.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import connection

PREFIX, SUFFIX = "db_", ".sqlite3"


class BackupError(Exception):
    pass


def backup_dir() -> Path:
    return Path(getattr(settings, "DB_BACKUP_DIR", Path(settings.BASE_DIR) / "backups"))


def database_file() -> Path | None:
    """Шлях до файлу робочої SQLite-бази; None — інший рушій, пам'ять або файла ще немає."""
    cfg = connection.settings_dict
    if "sqlite3" not in cfg["ENGINE"]:
        return None
    name = str(cfg["NAME"])
    if name == ":memory:" or name.startswith("file:"):
        return None
    path = Path(name)
    return path if path.is_file() else None


def list_backups(directory: Path | None = None) -> list[Path]:
    """Копії від найновішої до найстарішої."""
    directory = directory or backup_dir()
    if not directory.is_dir():
        return []
    return sorted(directory.glob(f"{PREFIX}*{SUFFIX}"), key=lambda p: p.name, reverse=True)


def make_backup(keep: int | None = None, now: datetime | None = None) -> Path | None:
    """Робить копію бази й прибирає старі. None — нема що копіювати (не файл SQLite)."""
    source = database_file()
    if source is None:
        return None
    keep = keep if keep is not None else getattr(settings, "DB_BACKUP_KEEP", 10)
    if keep < 1:
        raise BackupError("backup-keep має бути ≥ 1")
    directory = backup_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
        target = directory / f"{PREFIX}{stamp}{SUFFIX}"
        n = 1
        while target.exists():                           # дві копії за одну секунду
            target = directory / f"{PREFIX}{stamp}_{n}{SUFFIX}"
            n += 1
        src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    except (OSError, sqlite3.Error) as exc:
        raise BackupError(str(exc)) from exc
    for old in list_backups(directory)[keep:]:
        old.unlink(missing_ok=True)
    return target
