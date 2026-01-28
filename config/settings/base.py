"""
Django settings for SailArchive project.
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-development-key')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',  # For template filters like intcomma
    
    # Third-party apps
    'rest_framework',
    'django_extensions',
    'django_q',
    'registration',
    'storages',
    
    # Local apps
    'apps.core',
    'apps.tracks',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# WhiteNoise configuration
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Custom User Model (email-based authentication)
AUTH_USER_MODEL = 'core.User'


# Authentication settings
AUTHENTICATION_BACKENDS = [
    'apps.core.authentication_backend.EmailBackend',  # Email-based authentication
    'django.contrib.auth.backends.ModelBackend',  # Fallback
]

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_URL = '/accounts/login/'


# Django Registration Redux settings
ACCOUNT_ACTIVATION_DAYS = 7
REGISTRATION_AUTO_LOGIN = True
REGISTRATION_OPEN = True
REGISTRATION_FORM = 'apps.core.forms.EmailRegistrationForm'


# REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}


# Django-Q2 settings (async task queue using Postgres)
Q_CLUSTER = {
    'name': 'sailarchive',
    'workers': 2,
    'timeout': 300,  # 5 minutes max per task
    'retry': 360,
    'queue_limit': 50,
    'bulk': 10,
    'orm': 'default',  # Use the default database as broker
}


# DigitalOcean Spaces settings (S3-compatible storage for track files)
DO_SPACES_KEY = os.environ.get('DO_SPACES_KEY')
DO_SPACES_SECRET = os.environ.get('DO_SPACES_SECRET')
DO_SPACES_NAME = os.environ.get('DO_SPACES_NAME')
DO_SPACES_ENDPOINT = os.environ.get('DO_SPACES_ENDPOINT')
DO_SPACES_REGION = os.environ.get('DO_SPACES_REGION', 'sfo3')

# Configure storage if DO Spaces credentials are provided
if DO_SPACES_KEY and DO_SPACES_SECRET and DO_SPACES_NAME:
    AWS_ACCESS_KEY_ID = DO_SPACES_KEY
    AWS_SECRET_ACCESS_KEY = DO_SPACES_SECRET
    AWS_STORAGE_BUCKET_NAME = DO_SPACES_NAME
    AWS_S3_ENDPOINT_URL = DO_SPACES_ENDPOINT
    AWS_S3_REGION_NAME = DO_SPACES_REGION
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    
    # Use custom storage for media files (vessel icons, etc.)
    # This will be overridden in production.py to use DO Spaces
    DEFAULT_FILE_STORAGE = 'apps.tracks.storage.MediaStorage'


# Track file settings
TRACK_ZOOM_LEVELS = {
    'z6': 50,      # ~50 points for continental view
    'z10': 200,    # ~200 points for regional view
    'z14': 1000,   # ~1000 points for local view
    'z18': 5000,   # ~5000 points for detail view
}
TRACK_S3_PREFIX = 'tracks/'


# Email settings (can be overridden in production)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
