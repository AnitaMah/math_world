from django.db import migrations, models


def seed_math_subject(apps, schema_editor):
    Subject = apps.get_model("education", "Subject")
    Subject.objects.get_or_create(
        code="math",
        defaults={"name_uk": "Математика", "name_de": "Mathematik"},
    )


def noop_reverse(apps, schema_editor):
    # Intentionally left as a no-op: removing the seeded row on reverse
    # would delete data a later migration may already depend on. Deleting
    # the Subject table itself (the CreateModel below) is enough to undo
    # this migration structurally.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("education", "0007_remove_item_theory_paragraph_map_x_paragraph_map_y_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Subject",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.CharField(max_length=50, unique=True)),
                ("name_uk", models.CharField(max_length=100)),
                ("name_de", models.CharField(blank=True, max_length=100, null=True)),
            ],
        ),
        migrations.RunPython(seed_math_subject, noop_reverse),
    ]
