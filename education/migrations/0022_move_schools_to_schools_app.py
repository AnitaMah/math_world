# BE-S02: School/SchoolMembership/SchoolClass/SchoolClassStudent переїжджають у
# застосунок `schools` (docs/backend/DECISIONS.md — нуль FK у каталог, найбезпечніший
# кандидат на винесення першим). Це міняє лише стан Django, не БД: жодного
# database_operations, таблиці education_school* лишаються як є з тими самими даними.
# Дзеркальна міграція: schools/migrations/0001_initial.py.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('education', '0021_schoolclass_schoolclassstudent'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name='SchoolClassStudent'),
                migrations.DeleteModel(name='SchoolClass'),
                migrations.DeleteModel(name='SchoolMembership'),
                migrations.DeleteModel(name='School'),
            ],
        ),
    ]
