# Generated migration for adding share_token to Event model

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('tracks', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='share_token',
            field=models.UUIDField(
                default=uuid.uuid4,
                unique=True,
                db_index=True,
                help_text='Unique token for sharing this event and allowing anonymous uploads'
            ),
        ),
    ]
