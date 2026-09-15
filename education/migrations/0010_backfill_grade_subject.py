from django.db import migrations


def backfill_subject(apps, schema_editor):
    Grade = apps.get_model("education", "Grade")
    Subject = apps.get_model("education", "Subject")
    math_subject, _ = Subject.objects.get_or_create(
        code="math",
        defaults={"name_uk": "Математика", "name_de": "Mathematik"},
    )
    Grade.objects.filter(subject__isnull=True).update(subject=math_subject)


def reverse_backfill(apps, schema_editor):
    # Reversible in the structural sense (clears the FK back to null);
    # does not attempt to "un-seed" the Subject row itself.
    Grade = apps.get_model("education", "Grade")
    Grade.objects.all().update(subject=None)


class Migration(migrations.Migration):

    dependencies = [
        ("education", "0009_grade_subject"),
    ]

    operations = [
        migrations.RunPython(backfill_subject, reverse_backfill),
    ]
