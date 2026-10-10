"""0876: автобекап БД перед import_textbook."""
import io
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from education import backup


def make_db(path, rows=3):
    con = sqlite3.connect(path)
    con.execute("create table t (x integer)")
    con.executemany("insert into t values (?)", [(i,) for i in range(rows)])
    con.commit()
    con.close()


class BackupTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "db.sqlite3"
        make_db(self.db)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        cfg = {"ENGINE": "django.db.backends.sqlite3", "NAME": str(self.db)}
        p = mock.patch.object(backup.connection, "settings_dict", cfg)
        p.start()
        self.addCleanup(p.stop)
        o = override_settings(DB_BACKUP_DIR=str(self.tmp / "backups"), DB_BACKUP_KEEP=3)
        o.enable()
        self.addCleanup(o.disable)

    def test_backup_is_valid_copy(self):
        path = backup.make_backup()
        self.assertTrue(path.name.startswith("db_") and path.suffix == ".sqlite3")
        self.assertEqual(sqlite3.connect(path).execute("select count(*) from t").fetchone()[0], 3)

    def test_same_second_does_not_overwrite(self):
        now = datetime(2026, 10, 10, 12, 0, 0)
        a, b = backup.make_backup(now=now), backup.make_backup(now=now)
        self.assertNotEqual(a, b)
        self.assertEqual(len(backup.list_backups()), 2)

    def test_keeps_only_newest(self):
        start = datetime(2026, 10, 10, 12, 0, 0)
        made = [backup.make_backup(now=start + timedelta(minutes=i)) for i in range(5)]
        left = backup.list_backups()
        self.assertEqual(left, [made[4], made[3], made[2]])          # найновіші першими
        self.assertFalse(made[0].exists())

    def test_in_memory_or_missing_db_is_skipped(self):
        cfg = {"ENGINE": "django.db.backends.sqlite3", "NAME": "file:memorydb_default?mode=memory&cache=shared"}
        with mock.patch.object(backup.connection, "settings_dict", cfg):
            self.assertIsNone(backup.make_backup())
        cfg = {"ENGINE": "django.db.backends.postgresql", "NAME": "x"}
        with mock.patch.object(backup.connection, "settings_dict", cfg):
            self.assertIsNone(backup.make_backup())
        self.assertEqual(backup.list_backups(), [])

    def test_bad_keep(self):
        with self.assertRaises(backup.BackupError):
            backup.make_backup(keep=0)


class ImportCommandBackupTests(SimpleTestCase):
    """import_textbook: бекап до запису, не в dry-run, --no-backup, помилка бекапу зупиняє імпорт."""

    def run_cmd(self, *args):
        out = io.StringIO()
        with mock.patch("education.management.commands.import_textbook.TextbookImporter") as imp:
            imp.from_file.return_value.run.return_value = mock.Mock(
                as_stats=lambda: {}, warnings=[], dry_run=False, textbook_id=1, import_run_id=1)
            with mock.patch("education.management.commands.import_textbook.backup.make_backup",
                            return_value=Path("backups/db_x.sqlite3")) as mk:
                call_command("import_textbook", "--json", __file__, *args, stdout=out)
        return out.getvalue(), mk, imp

    def test_backup_before_import(self):
        out, mk, imp = self.run_cmd()
        mk.assert_called_once_with(keep=None)
        self.assertIn("Бекап БД", out)
        imp.from_file.assert_called_once()

    def test_dry_run_and_no_backup_skip_it(self):
        self.assertFalse(self.run_cmd("--dry-run")[1].called)
        self.assertFalse(self.run_cmd("--no-backup")[1].called)

    def test_backup_keep_passed(self):
        mk = self.run_cmd("--backup-keep", "5")[1]
        mk.assert_called_once_with(keep=5)

    def test_backup_error_stops_import(self):
        with mock.patch("education.management.commands.import_textbook.TextbookImporter") as imp, \
             mock.patch("education.management.commands.import_textbook.backup.make_backup",
                        side_effect=backup.BackupError("диск повний")):
            with self.assertRaisesRegex(CommandError, "Бекап не вдався"):
                call_command("import_textbook", "--json", __file__, stdout=io.StringIO())
        imp.from_file.assert_not_called()
