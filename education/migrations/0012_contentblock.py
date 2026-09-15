import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("education", "0011_grade_subject_required"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContentBlock",
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
                (
                    "block_type",
                    models.CharField(
                        choices=[
                            ("theory", "Теорія"),
                            ("self_check", "Самоперевірка (❓)"),
                            ("oral_exercise", "Розв'язуємо усно"),
                            ("exercise", "Вправа"),
                            ("review_exercise", "Вправа для повторення"),
                            ("wise_owl", "Задача від Мудрої Сови"),
                            ("history_aside", "Коли зроблено уроки"),
                        ],
                        max_length=20,
                    ),
                ),
                ("order", models.PositiveIntegerField(default=0)),
                ("text", models.TextField()),
                (
                    "difficulty",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("basic", "° початковий"),
                            ("standard", "стандартний"),
                            ("advanced", "·· високий"),
                            ("olympiad", "* гурток/факультатив"),
                        ],
                        max_length=20,
                        null=True,
                    ),
                ),
                ("image_path", models.CharField(blank=True, max_length=255, null=True)),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="content_blocks",
                        to="education.item",
                    ),
                ),
            ],
            options={
                "ordering": ["item", "order"],
            },
        ),
    ]
