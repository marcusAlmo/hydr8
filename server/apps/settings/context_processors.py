"""Template context processors for the Settings app.

These expose tenant-scoped SystemConfig values to every template so that
shared layout partials (e.g. the idle lock-screen overlay in ``base.html``)
can read configuration without each view having to pass it through.
"""
from __future__ import annotations

from .selectors import get_lockscreen_timeout_minutes


def lockscreen_timeout(request) -> dict[str, int]:
    """Exposes the configured lockscreen idle timeout (in minutes) to templates.

    Returns ``{'lockscreen_timeout_minutes': <int>}`` for authenticated
    users, where ``0`` means "Never" (lock screen disabled).  For
    anonymous users (login/onboarding pages) the value is ``0`` so the
    overlay never arms.
    """
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return {'lockscreen_timeout_minutes': 0}
    try:
        minutes = get_lockscreen_timeout_minutes(user)
    except Exception:
        # Never break rendering — fall back to "disabled".
        minutes = 0
    return {'lockscreen_timeout_minutes': minutes}
