from django.db import migrations


def forwards(apps, schema_editor):
    """Розділи без підручника отримують його, якщо для класу є рівно один Textbook (інакше лишаються як є).

    Код навмисно самодостатній (BE-S09, docs/backend/PLAN.md): раніше імпортував
    education.legacy.backfill_section_textbooks, але застосунковий код може змінюватись
    або зникати, а міграції мають лишатись відтворюваними з нуля назавжди.
    """
    Section = apps.get_model("education", "Section")
    Textbook = apps.get_model("education", "Textbook")
    by_grade = {}
    for tb in Textbook.objects.all():
        by_grade.setdefault(tb.grade_id, []).append(tb)
    for section in Section.objects.filter(textbook__isnull=True):
        tbs = by_grade.get(section.grade_id, [])
        if len(tbs) == 1:
            section.textbook = tbs[0]
            section.save(update_fields=["textbook"])


class Migration(migrations.Migration):
    dependencies = [("education", "0018_manual_edit_review")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
