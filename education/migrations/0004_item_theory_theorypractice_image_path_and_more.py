"""Empty stub migration to restore migration graph consistency.

This project has `0005_grade_name_de_grade_theme_de_grade_theme_uk_and_more.py`
which depends on `0004_item_theory_theorypractice_image_path_and_more`, but
the original `0004` file is missing from the repo. Creating this empty
stub allows Django to resolve the graph so you can run migrations.

If you have the original `0004` contents (from VCS or backup), restore it
instead of using this stub. After restoring real migrations, remove this
stub file.
"""

from django.db import migrations


class Migration(migrations.Migration):

    # Make this stub follow the initial migration so the graph has a single
    # linear path: 0001_initial -> 0004 -> 0005. This file is intentionally
    # empty; restore original operations if you have them.
    dependencies = [
        ("education", "0001_initial"),
    ]

    operations = []
