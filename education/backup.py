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


# ---------------------------------------------------------------- відкат (0877)
SAFETY_PREFIX = "before_restore_"
SAFETY_KEEP = 3


def resolve_backup(name: str | None = None) -> Path:
    """Копія за іменем (або шляхом); без імені — найновіша."""
    if name:
        for cand in (Path(name), backup_dir() / name):
            if cand.is_file():
                return cand
        raise BackupError(f"Копію не знайдено: {name}")
    found = list_backups()
    if not found:
        raise BackupError(f"У {backup_dir()} немає жодної копії")
    return found[0]


def check_backup(path: Path) -> int:
    """Перевіряє, що файл — цілісна SQLite-база з таблицями education_*; повертає кількість вправ."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if con.execute("pragma integrity_check").fetchone()[0] != "ok":
                raise BackupError(f"{path.name}: integrity_check не пройдено")
            return con.execute("select count(*) from education_exercise").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise BackupError(f"{path.name}: не схоже на базу math_world ({exc})") from exc


def restore(path: Path) -> Path:
    """Повертає базу з копії. Перед цим поточну зберігає як before_restore_*.sqlite3 (не входить у ротацію).

    Повертає шлях до копії поточної бази. Дані пишуться в той самий файл через sqlite3 backup API.
    """
    target = database_file()
    if target is None:
        raise BackupError("Відкат підтримується лише для файлової бази SQLite")
    check_backup(path)
    directory = backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    safety = directory / f"{SAFETY_PREFIX}{datetime.now().strftime('%Y%m%d_%H%M%S')}{SUFFIX}"
    n = 1
    while safety.exists():
        safety = directory / f"{SAFETY_PREFIX}{datetime.now().strftime('%Y%m%d_%H%M%S')}_{n}{SUFFIX}"
        n += 1
    connection.close()
    try:
        cur = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
        keep = sqlite3.connect(safety)
        try:
            cur.backup(keep)
        finally:
            keep.close()
            cur.close()
        src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    except (OSError, sqlite3.Error) as exc:
        raise BackupError(f"Відкат не вдався ({exc}). Закрий runserver/shell, що тримають базу, і повтори") from exc
    for old in sorted(directory.glob(f"{SAFETY_PREFIX}*{SUFFIX}"), key=lambda p: p.name, reverse=True)[SAFETY_KEEP:]:
        old.unlink(missing_ok=True)
    return safety
