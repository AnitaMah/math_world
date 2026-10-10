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


class RestoreTests(BackupTests):
    """Відкат: спершу зберігає поточну базу, потім повертає вміст копії."""

    def count(self, path=None):
        return sqlite3.connect(path or self.db).execute("select count(*) from t").fetchone()[0]

    def prepare(self, rows_in_backup=3):
        # check_backup шукає education_exercise → додамо таблицю до бази й копії
        sqlite3.connect(self.db).executescript("create table education_exercise (id integer);"
                                               "insert into education_exercise values (1);")
        bk = backup.make_backup()
        con = sqlite3.connect(self.db)
        con.execute("insert into t values (99)")
        con.commit(); con.close()
        return bk

    def test_restore_returns_old_content_and_keeps_safety_copy(self):
        bk = self.prepare()
        self.assertEqual(self.count(), 4)
        safety = backup.restore(bk)
        self.assertEqual(self.count(), 3)                       # повернулась стара база
        self.assertEqual(self.count(safety), 4)                 # а поточну збережено
        self.assertTrue(safety.name.startswith("before_restore_"))
        self.assertNotIn(safety, backup.list_backups())         # не бере участі в ротації автобекапів

    def test_resolve_latest_and_by_name(self):
        bk = self.prepare()
        self.assertEqual(backup.resolve_backup(), bk)
        self.assertEqual(backup.resolve_backup(bk.name), bk)
        with self.assertRaises(backup.BackupError):
            backup.resolve_backup("nope.sqlite3")

    def test_bad_file_rejected_and_db_untouched(self):
        bad = self.tmp / "bad.sqlite3"
        bad.write_bytes(b"not a database at all")
        with self.assertRaises(backup.BackupError):
            backup.restore(bad)
        self.assertEqual(self.count(), 3)

    def test_safety_copies_rotate(self):
        bk = self.prepare()
        for _ in range(5):
            backup.restore(bk)
        self.assertEqual(len(list(backup.backup_dir().glob("before_restore_*"))), backup.SAFETY_KEEP)

    def test_command_dry_then_yes(self):
        bk = self.prepare()
        out = io.StringIO()
        call_command("restore_db", "--latest", stdout=out)
        self.assertIn("Нічого не змінено", out.getvalue())
        self.assertEqual(self.count(), 4)
        out = io.StringIO()
        call_command("restore_db", "--file", bk.name, "--yes", stdout=out)
        self.assertIn("Базу відкочено", out.getvalue())
        self.assertEqual(self.count(), 3)

    def test_command_list_and_errors(self):
        out = io.StringIO()
        call_command("restore_db", stdout=out)
        self.assertIn("немає копій", out.getvalue())
        with self.assertRaises(CommandError):
            call_command("restore_db", "--latest", stdout=io.StringIO())
        self.prepare()
        out = io.StringIO()
        call_command("restore_db", stdout=out)
        self.assertIn("db_", out.getvalue())
