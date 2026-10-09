from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('education', '0016_game_progress'),
    ]

    operations = [
        migrations.AddField(
            model_name='item',
            name='map_x',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='item',
            name='map_y',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
