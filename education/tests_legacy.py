"""21В.2: старі блоки, backfill Section.textbook, порівняння з копією БД, data-міграція 0019."""
import io
import sqlite3
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from education import legacy
from education.models import ContentBlock, Grade, Item, Paragraph, Section, Subject, Textbook


def make_tree(grade_number=5, textbook=True, tb_kwargs=None):
    subject, _ = Subject.objects.get_or_create(code="math", defaults={"name_uk": "Математика"})
    grade, _ = Grade.objects.get_or_create(subject=subject, number=grade_number)
    tb = Textbook.objects.create(subject=subject, grade=grade, profile_code=f"m{grade_number}",
                                 title="Т", pdf_sha256=f"sha{grade_number}") if textbook else None
    sec = Section.objects.create(grade=grade, number=1, name_uk="Розділ I", textbook=None)
    par = Paragraph.objects.create(section=sec, number=1, name_uk="§ 1")
    item = Item.objects.create(paragraph=par, number=1, content="Пункт")
    return tb, sec, par, item


class LegacyBlocksTests(TestCase):
    def setUp(self):
        self.tb, self.sec, self.par, self.item = make_tree()

    def block(self, **kw):
        kw.setdefault("block_type", "theory")
        kw.setdefault("item", self.item)
        return ContentBlock.objects.create(**kw)

    def test_report_does_not_change_anything(self):
        self.block()                                     # старий
        self.block(source_page=3)                        # новий
        rep = legacy.audit(apply=False)
        self.assertEqual((rep.legacy_blocks, rep.deletable, rep.sections_backfillable), (1, 1, 1))
        self.assertEqual(ContentBlock.objects.count(), 2)
        self.assertIsNone(Section.objects.get().textbook)

    def test_apply_deletes_only_covered_non_manual(self):
        covered = self.block()
        manual = self.block(text_source="manual", block_type="rule")
        keep_new = self.block(source_page=3)
        other = Item.objects.create(paragraph=self.par, number=2, content="Пункт 2")
        alone = self.block(item=other)                   # у цьому пункті нових блоків ще немає
        rep = legacy.audit(apply=True)
        left = set(ContentBlock.objects.values_list("pk", flat=True))
        self.assertEqual(left, {manual.pk, keep_new.pk, alone.pk})
        self.assertNotIn(covered.pk, left)
        self.assertEqual((rep.kept_manual, rep.kept_no_new), (1, 1))
        self.assertEqual(Section.objects.get().textbook, self.tb)

    def test_paragraph_level_blocks(self):
        ContentBlock.objects.create(paragraph=self.par, block_type="summary")
        ContentBlock.objects.create(paragraph=self.par, block_type="self_test", source_page=9)
        legacy.audit(apply=True)
        self.assertEqual(list(ContentBlock.objects.values_list("block_type", flat=True)), ["self_test"])

    def test_idempotent(self):
        self.block(); self.block(source_page=3)
        legacy.audit(apply=True)
        rep = legacy.audit(apply=True)
        self.assertEqual((rep.legacy_blocks, rep.sections_backfillable, rep.sections_without_textbook), (0, 0, 0))

    def test_grade_without_textbook_stays_orphan(self):
        _, sec6, _, _ = make_tree(6, textbook=False)
        rep = legacy.audit(apply=True)
        sec6.refresh_from_db()
        self.assertIsNone(sec6.textbook)
        self.assertEqual(rep.sections_orphan, [(6, 1)])
        self.assertEqual(rep.items_without_textbook, 1)

    def test_two_textbooks_for_grade_is_ambiguous(self):
        Textbook.objects.create(subject=self.tb.subject, grade=self.tb.grade, profile_code="other",
                                title="Інший", pdf_sha256="zzz")
        legacy.audit(apply=True)
        self.assertIsNone(Section.objects.get().textbook)

    def test_command_report_and_apply(self):
        self.block(); self.block(source_page=3)
        buf = io.StringIO()
        call_command("migrate_legacy_data", stdout=buf)
        self.assertIn("можна видалити: 1", buf.getvalue())
        self.assertEqual(ContentBlock.objects.count(), 2)
        buf = io.StringIO()
        call_command("migrate_legacy_data", "--apply", stdout=buf)
        self.assertEqual(ContentBlock.objects.count(), 1)

    def test_compare_with_old_db(self):
        self.block(source_page=3)
        self.block(source_page=4, block_type="rule")
        tmp = Path(tempfile.mkdtemp()) / "old.sqlite3"
        con = sqlite3.connect(tmp)
        con.executescript("""
            create table education_grade(id integer primary key, number int);
            create table education_section(id integer primary key, grade_id int, number int);
            create table education_paragraph(id integer primary key, section_id int, number int);
            create table education_item(id integer primary key, paragraph_id int, number int);
            create table education_contentblock(id integer primary key, item_id int, paragraph_id int, block_type text);
            insert into education_grade values (1, 5);
            insert into education_section values (1, 1, 1);
            insert into education_paragraph values (1, 1, 1);
            insert into education_item values (1, 1, 1);
            insert into education_contentblock values (1, 1, null, 'theory'), (2, 1, null, 'theory'), (3, 1, null, 'oral_exercise');
        """)
        con.commit(); con.close()
        old = legacy.old_block_counts(str(tmp))
        rows = legacy.compare(old, legacy.new_block_counts())
        self.assertEqual(rows, [((5, 1, 1, 1, "oral_exercise"), 1, 0), ((5, 1, 1, 1, "rule"), 0, 1),
                                ((5, 1, 1, 1, "theory"), 2, 1)])
        md = legacy.comparison_markdown(rows, 3, 2, "old.sqlite3")
        self.assertIn("| 5 | 1 | 1 | 1 | theory | 2 | 1 |", md)


class BackfillMigrationTests(TransactionTestCase):
    """Data-міграція 0019 на «старих» даних: розділ без підручника отримує його."""
    migrate_from = [("education", "0018_manual_edit_review")]
    migrate_to = [("education", "0019_backfill_section_textbook")]

    def test_forwards(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        Subject_, Grade_, Textbook_, Section_ = (apps.get_model("education", n)
                                                  for n in ("Subject", "Grade", "Textbook", "Section"))
        subject = Subject_.objects.create(code="m2", name_uk="М")
        g5, g6 = Grade_.objects.create(subject=subject, number=5), Grade_.objects.create(subject=subject, number=6)
        tb = Textbook_.objects.create(subject=subject, grade=g5, profile_code="x", title="T", pdf_sha256="s")
        s5 = Section_.objects.create(grade=g5, number=1, name_uk="a")
        s6 = Section_.objects.create(grade=g6, number=1, name_uk="b")

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        Section_ = apps.get_model("education", "Section")
        self.assertEqual(Section_.objects.get(pk=s5.pk).textbook_id, tb.pk)
        self.assertIsNone(Section_.objects.get(pk=s6.pk).textbook_id)

    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
