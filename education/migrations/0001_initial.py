"""Initial migration: create models as they currently exist in `models.py`.

This migration is created to restore a consistent migration graph in the
repository. If you have original migrations from VCS, prefer restoring
those instead of using this generated initial migration.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Grade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.IntegerField()),
                ("name_uk", models.CharField(max_length=100)),
                ("name_de", models.CharField(max_length=100, null=True, blank=True)),
                ("theme_uk", models.CharField(max_length=200, null=True, blank=True)),
                ("theme_de", models.CharField(max_length=200, null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name="Section",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.IntegerField()),
                ("name_uk", models.CharField(max_length=200)),
                ("name_de", models.CharField(max_length=200, null=True, blank=True)),
                ("grade", models.ForeignKey(on_delete=models.CASCADE, to="education.Grade")),
            ],
        ),
        migrations.CreateModel(
            name="Paragraph",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.IntegerField()),
                ("name_uk", models.CharField(max_length=200)),
                ("name_de", models.CharField(max_length=200, null=True, blank=True)),
                ("section", models.ForeignKey(on_delete=models.CASCADE, to="education.Section")),
            ],
        ),
        migrations.CreateModel(
            name="Item",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.IntegerField()),
                ("content", models.TextField()),
                ("content_de", models.TextField(null=True, blank=True)),
                ("type", models.CharField(default="основний", max_length=50)),
                ("image_path", models.CharField(max_length=255, null=True, blank=True)),
                ("theory", models.TextField(null=True, blank=True)),
                ("paragraph", models.ForeignKey(on_delete=models.CASCADE, to="education.Paragraph")),
            ],
        ),
        migrations.CreateModel(
            name="TheoryPractice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("theory", models.TextField(blank=True)),
                ("practice", models.TextField(blank=True)),
                ("image_path", models.CharField(max_length=255, null=True, blank=True)),
                ("item", models.OneToOneField(on_delete=models.CASCADE, to="education.Item")),
            ],
        ),
        migrations.CreateModel(
            name="Lesson",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("content", models.TextField()),
                ("image", models.ImageField(upload_to="lessons/", null=True, blank=True)),
            ],
        ),
    ]
