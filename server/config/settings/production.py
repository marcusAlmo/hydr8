from .base import *

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

DEBUG = env.bool('DEBUG', default=False)

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

# Production-specific settings like CSRF_COOKIE_SECURE, SESSION_COOKIE_SECURE, etc.
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# Behind Cloudflare → Traefik → Gunicorn. Trust the forwarded headers so
# Django sees the real scheme/host and CSRF origin checks pass.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# Trusted origins for CSRF — the production domain(s).
CSRF_TRUSTED_ORIGINS = env.list(
    'CSRF_TRUSTED_ORIGINS',
    default=['https://hydr8.npjn.store'],
)

# Production cache — Redis (the VPS already runs Redis on port 6379).
# Used by django-ratelimit and the login lockout logic. The shared, atomic
# counter is required so rate limits are enforced across all gunicorn workers.
REDIS_URL = env('REDIS_URL', default='redis://127.0.0.1:6379/1')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    }
}

# Persistent database connections — let gunicorn keep connections open for
# 10 minutes instead of creating a new one on every request.
DATABASES['default']['CONN_MAX_AGE'] = 600

SENTRY_DSN = env('SENTRY_DSN', default=None)

if not DEBUG and SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.0,
    )
