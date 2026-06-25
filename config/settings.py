import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-only-insecure-key-change-in-production'
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')
CSRF_TRUSTED_ORIGINS = os.environ.get('CSRF_TRUSTED_ORIGINS', 'http://localhost:8000').split(',')
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_celery_beat',
    'django_celery_results',
    'apps.users',
    'apps.whatsapp',
    'apps.contacts',
    'apps.difusiones',
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
AUTH_USER_MODEL = 'users.User'

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
                'apps.whatsapp.context_processors.unread_messages_count',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'waply'),
        'USER': os.environ.get('POSTGRES_USER', 'waply'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'waply123'),
        'HOST': os.environ.get('POSTGRES_HOST', 'db'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Redis / Celery
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = 'django-db'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_ROUTES = {
    'apps.whatsapp.*': {'queue': 'whatsapp'},
    'apps.difusiones.*': {'queue': 'default'},
}

# Proveedor de WhatsApp activo: 'meta' (Cloud API oficial) o 'twilio'.
# Se puede sobreescribir desde Configuración en la app; este es el valor por defecto.
PROVEEDOR = os.environ.get('WHATSAPP_PROVIDER', 'meta')

# WhatsApp Cloud API (Meta)
META_ACCESS_TOKEN = os.environ.get('META_ACCESS_TOKEN', '')
META_PHONE_NUMBER_ID = os.environ.get('META_PHONE_NUMBER_ID', '')
META_WABA_ID = os.environ.get('META_WABA_ID', '')
META_APP_SECRET = os.environ.get('META_APP_SECRET', '')
META_API_VERSION = os.environ.get('META_API_VERSION', 'v21.0')

# Verify token del handshake del webhook (Meta for Developers → WhatsApp → Configuración)
META_VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', '')

# Twilio (proveedor alternativo)
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_FROM = os.environ.get('TWILIO_WHATSAPP_FROM', '')

# n8n
N8N_WEBHOOK_URL = os.environ.get('N8N_WEBHOOK_URL', '')

# Webhook de n8n a notificar cuando el asesor reactiva el bot en una conversación
N8N_LIBERAR_ASESOR_URL = os.environ.get('N8N_LIBERAR_ASESOR_URL', '')

# CRM API Key (para n8n enviar mensajes)
CRM_API_KEY = os.environ.get('CRM_API_KEY', '')

# Login
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'apps.whatsapp': {'handlers': ['console'], 'level': 'INFO'},
        'apps.users': {'handlers': ['console'], 'level': 'INFO'},
    },
}
