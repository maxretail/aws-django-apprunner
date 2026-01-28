import os
import logging
from .base import *

logger = logging.getLogger(__name__)

DEBUG = False

# Security settings
ALLOWED_HOSTS = ['*']  # Allow all hosts in App Platform environment
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]

# Database configuration (DigitalOcean Managed PostgreSQL)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT', '25060'),  # DO managed DB default port
        'OPTIONS': {
            'sslmode': 'require',  # DO managed databases require SSL
        },
    }
}

# Security middleware settings
SECURE_SSL_REDIRECT = False  # Allow HTTP for health checks
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# Email configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp-relay.brevo.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@sailarchive.com')

# Media files storage - Use DO Spaces in production
# Ensure DO Spaces credentials are set via environment variables
if os.getenv('DO_SPACES_KEY') and os.getenv('DO_SPACES_SECRET') and os.getenv('DO_SPACES_NAME'):
    DEFAULT_FILE_STORAGE = 'apps.tracks.storage.MediaStorage'
    # Media files will be served from DO Spaces CDN
    # The MediaStorage class handles public-read ACL for easy access
    MEDIA_URL = f"https://{os.getenv('DO_SPACES_NAME')}.{os.getenv('DO_SPACES_REGION', 'sfo3')}.digitaloceanspaces.com/media/"
else:
    logger.warning("DO Spaces credentials not found. Media files will use local storage.")

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django_q': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.tracks': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
