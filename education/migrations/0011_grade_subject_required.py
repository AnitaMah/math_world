from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("education", "0010_backfill_grade_subject"),
    ]

    operations = [
        migrations.AlterField(
            model_name="grade",
            name="subject",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="education.subject",
            ),
        ),
    ]
