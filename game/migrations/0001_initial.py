# BE-S04: дзеркало education/migrations/0023_move_game_to_game_app.py — модель
# переїжджає лише в стані Django. Таблиці (education_player, education_attempt,
# education_lessonprogress) уже існують із усіма даними; db_table у
# game/models.py фіксує ці самі назви, тож жодного database_operations тут немає.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('education', '0023_move_game_to_game_app'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='Player',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('session_key', models.CharField(blank=True, max_length=64, null=True, unique=True)),
                        ('points', models.PositiveIntegerField(default=0)),
                        ('streak', models.PositiveIntegerField(default=0)),
                        ('last_active', models.DateField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('user', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='player', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'education_player',
                    },
                ),
                migrations.CreateModel(
                    name='LessonProgress',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('solved', models.PositiveIntegerField(default=0)),
                        ('total', models.PositiveIntegerField(default=0)),
                        ('points', models.PositiveIntegerField(default=0)),
                        ('stars', models.PositiveSmallIntegerField(default=0)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='progress', to='education.item')),
                        ('paragraph', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='progress', to='education.paragraph')),
                        ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='progress', to='game.player')),
                    ],
                    options={
                        'db_table': 'education_lessonprogress',
                        'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('item__isnull', False), ('paragraph__isnull', True)), models.Q(('item__isnull', True), ('paragraph__isnull', False)), _connector='OR'), name='progress_item_xor_paragraph'), models.UniqueConstraint(fields=('player', 'item'), name='progress_unique_item'), models.UniqueConstraint(fields=('player', 'paragraph'), name='progress_unique_paragraph')],
                    },
                ),
                migrations.CreateModel(
                    name='Attempt',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('kind', models.CharField(choices=[('auto', 'Автоперевірка'), ('ai', 'Перевірка ШІ')], default='auto', max_length=5)),
                        ('answer_text', models.TextField()),
                        ('correct', models.BooleanField(default=False)),
                        ('verdict', models.CharField(blank=True, choices=[('correct', 'Правильно'), ('incorrect', 'Неправильно'), ('unclear', 'Незрозуміло')], max_length=10)),
                        ('feedback', models.TextField(blank=True)),
                        ('points', models.PositiveIntegerField(default=0)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('exercise', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attempts', to='education.exercise')),
                        ('subexercise', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='attempts', to='education.subexercise')),
                        ('player', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attempts', to='game.player')),
                    ],
                    options={
                        'db_table': 'education_attempt',
                        'ordering': ['-created_at'],
                        'indexes': [models.Index(fields=['player', 'subexercise'], name='education_a_player__2faf92_idx'), models.Index(fields=['player', 'exercise'], name='education_a_player__6b6cce_idx')],
                    },
                ),
            ],
        ),
    ]
