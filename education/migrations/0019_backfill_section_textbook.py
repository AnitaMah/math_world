from django.db import migrations

from education.legacy import backfill_section_textbooks


def forwards(apps, schema_editor):
    """Розділи без підручника отримують його, якщо для класу є рівно один Textbook (інакше лишаються як є)."""
    backfill_section_textbooks(apps.get_model("education", "Section"), apps.get_model("education", "Textbook"))


class Migration(migrations.Migration):
    dependencies = [("education", "0018_manual_edit_review")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
