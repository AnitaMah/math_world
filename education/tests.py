from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from education.models import Grade, Section, Paragraph, Item


class ImportCurriculumCommandTests(TestCase):
    def setUp(self):
        self.sample_file = Path(settings.BASE_DIR) / "data" / "5_class_ukr.txt"

    def test_import_creates_full_hierarchy(self):
        call_command("import_curriculum", "--file", str(self.sample_file), "--grade", "5", "--language", "uk")

        grade = Grade.objects.get(number=5)
        self.assertEqual(grade.name_uk, "5 клас")
        self.assertEqual(Section.objects.filter(grade=grade).count(), 2)
        self.assertEqual(Paragraph.objects.filter(section__grade=grade).count(), 5)
        self.assertEqual(Item.objects.filter(paragraph__section__grade=grade).count(), 38)

    def test_import_merges_bullet_points_into_item(self):
        call_command("import_curriculum", "--file", str(self.sample_file), "--grade", "5", "--language", "uk")

        second_item = Item.objects.get(paragraph__section__grade__number=5, number=2)
        self.assertIn("Як рахували в давнину", second_item.content)
        self.assertIn("Як називають «числа-велетні»", second_item.content)
        self.assertTrue(second_item.content.startswith("Цифри. Десятковий запис натуральних чисел"))

    def test_reset_flag_removes_previous_grade_content_before_import(self):
        grade = Grade.objects.create(number=5, name_uk="5 клас")
        section = Section.objects.create(grade=grade, number=99, name_uk="Старий розділ")
        paragraph = Paragraph.objects.create(section=section, number=1, name_uk="Старий параграф")
        Item.objects.create(paragraph=paragraph, number=1, content="Старий пункт")

        call_command(
            "import_curriculum",
            "--file",
            str(self.sample_file),
            "--grade",
            "5",
            "--language",
            "uk",
            "--reset",
        )

        grade = Grade.objects.get(number=5)
        self.assertEqual(Section.objects.filter(grade=grade).count(), 2)
        self.assertFalse(Section.objects.filter(grade=grade, number=99).exists())
        self.assertEqual(Paragraph.objects.filter(section__grade=grade).count(), 5)
        self.assertEqual(Item.objects.filter(paragraph__section__grade=grade).count(), 38)
