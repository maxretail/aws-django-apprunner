from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import os
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

class Command(BaseCommand):
    help = 'Ensures a superuser exists with specified credentials'

    def handle(self, *args, **options):
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'devops@example.com')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
        username = email  # Use email as username

        if not password:
            self.stdout.write(self.style.ERROR('DJANGO_SUPERUSER_PASSWORD environment variable not set'))
            return

        try:
            user = User.objects.get(email=email)
            logger.info(f"User {email} already exists")
        except User.DoesNotExist:
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )
            logger.info(f"Created superuser {email}")

        self.stdout.write(self.style.SUCCESS(f'Superuser {email} is ready to use')) 