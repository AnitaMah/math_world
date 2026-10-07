"""Стара шкала складності ContentBlock (basic/standard/advanced/olympiad) → єдина шкала
пайплайна (preparatory/medium/sufficient/high/olympiad). Див. DECISIONS.md, фаза 8."""
from django.db import migrations

OLD_TO_NEW = {"basic": "medium", "standard": None, "advanced": "high", "olympiad": "olympiad"}
NEW_TO_OLD = {"medium": "basic", "high": "advanced", "olympiad": "olympiad"}


def forwards(apps, schema_editor):
    ContentBlock = apps.get_model("education", "ContentBlock")
    for old, new in OLD_TO_NEW.items():
        ContentBlock.objects.filter(difficulty=old).update(difficulty=new)


def backwards(apps, schema_editor):
    ContentBlock = apps.get_model("education", "ContentBlock")
    for new, old in NEW_TO_OLD.items():
        ContentBlock.objects.filter(difficulty=new).update(difficulty=old)


class Migration(migrations.Migration):
    dependencies = [("education", "0014_pipeline_models")]
    operations = [migrations.RunPython(forwards, backwards)]
