from pathlib import Path
import environ
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# BASE_DIR is the root of the project (hydr8)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Initialize environment variables
env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool('DEBUG', default=False)

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

# Application definition
INSTALLED_APPS = [
    'unfold',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party apps
    'django_htmx',
    'auditlog',
    # Local apps
    'apps.users',
    'apps.core',
    'apps.customers',
    'apps.remittance',
    'apps.analytics',
    'apps.settings',
]

MIDDLEWARE = [
    'apps.core.middleware.CorrelationIdMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.middleware.ScreenLockMiddleware',
    'auditlog.middleware.AuditlogMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

# django-auditlog — use the project's correlation id contextvar (set by
# CorrelationIdMiddleware) to populate LogEntry.cid. Without this, auditlog
# reads the X-Correlation-ID header independently and saves None for normal
# browser requests (which don't send the header). CorrelationIdMiddleware
# runs before AuditlogMiddleware, so the contextvar is always set first.
AUDITLOG_CID_GETTER = 'apps.core.middleware.get_correlation_id'

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors_settings.lockscreen_timeout',
                'apps.users.context_processors.user_role_flags',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database — PostgreSQL only.  DATABASE_URL must be set in the environment
# (e.g. postgres://user:pass@localhost:5432/hydr8).  No SQLite fallback.
DATABASES = {
    'default': env.db('DATABASE_URL')
}

# Caching — the cache backend is environment-specific:
#   * local.py    -> LocMemCache (no Redis required for dev)
#   * production  -> Redis (the VPS already runs Redis on port 6379)
#   * test.py     -> LocMemCache (hermetic test suite)
# django-ratelimit and the login lockout both use the 'default' cache.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'hydr8-default',
    }
}

# Rate limiting defaults — applied via the @ratelimit decorator on views.
# Login is the most abuse-prone endpoint; other endpoints use these as a baseline.
RATELIMIT_ENABLE = env.bool('RATELIMIT_ENABLE', default=True)
RATELIMIT_USE_CACHE = 'default'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
# Philippines is GMT+8 (Asia/Manila). The server/VPS may run in UTC or
# another OS timezone, but all "today" / display logic must resolve to PHT.
# USE_TZ stays True so datetimes are still stored as UTC in the database;
# timezone.localdate() / timezone.localtime() / template rendering all use
# this zone, and date.today()/datetime.now() (which use the OS timezone) are
# replaced with the timezone-aware helpers throughout the services layer.
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Login URL — @login_required redirects here. Points to the full landing page
# (users:index at '/') which renders users/index.html with the login form embedded.
# The HTMX login endpoint (users:login at '/login/') returns only the bare form
# partial on GET, so it must NOT be the LOGIN_URL target.
LOGIN_URL = 'users:index'
LOGIN_REDIRECT_URL = 'analytics:dashboard'

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'correlation_id': {
            '()': 'apps.core.middleware.CorrelationIdFilter',
        },
    },
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} [Correlation-ID: {correlation_id}] {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'filters': ['correlation_id'],
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
    },
}
