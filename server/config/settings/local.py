from .base import *

DEBUG = env.bool('DEBUG', default=True)

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1', '0.0.0.0'])

# Browser preview / ephemeral dev ports serve the page from a different origin
# (e.g. http://127.0.0.1:60925) than the Django server (e.g. :8765). Listing the
# scheme + host without a port matches any port on that host, so CSRF checks
# pass regardless of which ephemeral port the preview iframe uses.
CSRF_TRUSTED_ORIGINS = env.list(
    'CSRF_TRUSTED_ORIGINS',
    default=[
        'http://localhost',
        'http://127.0.0.1',
        'http://0.0.0.0',
    ],
)

# Local-specific apps or middleware (like debug toolbar) can be added here
