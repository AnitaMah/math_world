# BE-S04: Player/Attempt/LessonProgress переїжджають у застосунок `game`
# (docs/backend/DECISIONS.md — залежать від каталогу однобічно, каталог про гру
# не знає). Лише стан Django: жодного database_operations, таблиці
# education_player/attempt/lessonprogress лишаються як є з тими самими даними.
# Дзеркальна міграція: game/migrations/0001_initial.py.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('education', '0022_move_schools_to_schools_app'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name='LessonProgress'),
                migrations.DeleteModel(name='Attempt'),
                migrations.DeleteModel(name='Player'),
            ],
        ),
    ]
