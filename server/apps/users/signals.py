"""Custom signals for the users app.

These are fired at runtime (not import time) so there is no circular
dependency with apps.core (signals_audit) even though core connects receivers to them.
"""
from django.dispatch import Signal

# Fired when a login attempt fails.
# kwargs: request, username, ip
login_failed = Signal()
