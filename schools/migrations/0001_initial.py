# BE-S02: дзеркало education/migrations/0022_move_schools_to_schools_app.py —
# модель переїжджає лише в стані Django. Таблиці (education_school,
# education_schoolmembership, education_schoolclass, education_schoolclassstudent)
# уже існують із усіма даними; db_table у schools/models.py фіксує ці самі назви,
# тож жодного database_operations тут немає.
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('education', '0022_move_schools_to_schools_app'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='School',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('name', models.CharField(max_length=255)),
                        ('country', models.CharField(choices=[('UA', 'Україна'), ('DE', 'Deutschland')], default='UA', max_length=2)),
                        ('official_number', models.CharField(help_text='Офіційний номер: код ЄДЕБО (UA) або Schulnummer (DE)', max_length=32, validators=[django.core.validators.RegexValidator('^[0-9A-Za-z-]{3,32}$', 'Лише цифри, латинські літери та дефіс')])),
                        ('city', models.CharField(blank=True, max_length=100)),
                        ('status', models.CharField(choices=[('pending', 'Очікує перевірки'), ('verified', 'Офіційна (верифікована)'), ('rejected', 'Відхилена')], db_index=True, default='pending', max_length=10)),
                        ('verified_at', models.DateTimeField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='registered_schools', to=settings.AUTH_USER_MODEL)),
                        ('verified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='verified_schools', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'education_school',
                        'ordering': ['name'],
                    },
                ),
                migrations.CreateModel(
                    name='SchoolMembership',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('role', models.CharField(choices=[('school_admin', 'Адміністратор школи'), ('teacher', 'Вчитель')], default='teacher', max_length=20)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('added_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='schools.school')),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='school_memberships', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'education_schoolmembership',
                        'ordering': ['school', 'role', 'user__username'],
                    },
                ),
                migrations.CreateModel(
                    name='SchoolClass',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('name', models.CharField(max_length=100)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('school', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='classes', to='schools.school')),
                        ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='taught_classes', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'education_schoolclass',
                        'ordering': ['school', 'name'],
                    },
                ),
                migrations.CreateModel(
                    name='SchoolClassStudent',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('added_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                        ('school_class', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='students', to='schools.schoolclass')),
                        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='class_memberships', to=settings.AUTH_USER_MODEL)),
                    ],
                    options={
                        'db_table': 'education_schoolclassstudent',
                        'ordering': ['school_class', 'user__username'],
                        'constraints': [models.UniqueConstraint(fields=('school_class', 'user'), name='class_student_unique')],
                    },
                ),
                migrations.AddConstraint(
                    model_name='school',
                    constraint=models.UniqueConstraint(fields=('country', 'official_number'), name='school_unique_official_number'),
                ),
                migrations.AddConstraint(
                    model_name='school',
                    constraint=models.CheckConstraint(condition=models.Q(models.Q(('status', 'verified'), _negated=True), ('verified_at__isnull', False), _connector='OR'), name='school_verified_has_date'),
                ),
                migrations.AddConstraint(
                    model_name='schoolmembership',
                    constraint=models.UniqueConstraint(fields=('school', 'user'), name='school_membership_unique'),
                ),
            ],
        ),
    ]
