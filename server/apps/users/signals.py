"""Custom signals for the users app.

These are fired at runtime (not import time) so there is no circular
dependency with apps.audit even though audit connects receivers to them.
"""
from django.dispatch import Signal

# Fired when a login attempt fails.
# kwargs: request, username, ip
login_failed = Signal()
