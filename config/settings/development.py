import os
from .base import *

DEBUG = True

ALLOWED_HOSTS = ['*']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'postgres',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': 'db',
        'PORT': '5432',
    }
}

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Use local filesystem for media files in development
# Override the base setting to use local storage
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# Use console email backend in development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Django-Q2 settings for development (smaller cluster)
Q_CLUSTER = {
    'name': 'sailarchive-dev',
    'workers': 1,
    'timeout': 300,
    'retry': 360,
    'queue_limit': 50,
    'orm': 'default',
}

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
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
        'django.urls': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'apps.core': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'apps.tracks': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'django_q': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
