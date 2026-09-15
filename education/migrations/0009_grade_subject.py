from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("education", "0008_subject"),
    ]

    operations = [
        migrations.AddField(
            model_name="grade",
            name="subject",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="education.subject",
            ),
        ),
    ]
