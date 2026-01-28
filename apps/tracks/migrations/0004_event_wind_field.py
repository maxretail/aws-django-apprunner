from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tracks', '0003_add_crop_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventWindField',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('grid_size', models.PositiveSmallIntegerField(default=6)),
                ('interval_minutes', models.PositiveSmallIntegerField(default=30)),
                ('bounding_box', models.JSONField()),
                ('start_time', models.DateTimeField()),
                ('end_time', models.DateTimeField()),
                ('data', models.JSONField(default=dict)),
                ('computed_at', models.DateTimeField(auto_now=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wind_fields', to='tracks.event')),
            ],
            options={
                'unique_together': {('event', 'grid_size', 'interval_minutes')},
            },
        ),
    ]
