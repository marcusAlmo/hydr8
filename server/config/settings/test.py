from .base import *

DEBUG = False

# PostgreSQL only — mirrors the production engine.  The test runner creates
# a separate ``hydr8_test`` database so the dev DB is never clobbered.
# DATABASE_URL must still point at the Postgres cluster; we only swap the
# db name so parallel test runs don't collide with development data.
DATABASES = {
    'default': env.db('DATABASE_URL', default='postgres://dasher:admin@localhost:5432/hydr8_test')
}

# Tests use LocMemCache so the suite is hermetic and does not require a running
# Redis instance. Rate limiting still works (counters live in process memory).
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'hydr8-test',
    }
}

# NOTE: Migrations are NOT disabled — with Postgres + RLS policies the test
# DB must run the real migration chain (including RLS-enabling migrations) so
# that row-level isolation is exercised under test.
