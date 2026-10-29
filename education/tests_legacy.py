"""Data-міграція 0019: розділ без підручника отримує його, якщо для класу є рівно один Textbook.

BE-S09 (docs/backend/PLAN.md): education/legacy.py й management-команда migrate_legacy_data
видалені — одноразове прибирання старих блоків із фази 21В.2 вже застосоване всюди.
Цей тест лишається, бо перевіряє саму міграцію 0019 (яка тепер самодостатня), а не той
інструментарій.
"""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


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
