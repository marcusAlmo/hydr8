"""Template context processors for the Users app.

Exposes role-based authorization flags to every template so shared layout
partials (e.g. the sidebar) can conditionally show/hide navigation items
without each view having to pass them through manually.

The flags mirror the helpers in ``apps.users.permissions``:

  * ``is_staff_role_user``  — True only for the Staff role (focused/limited view)
  * ``is_admin_user``       — True for Admin role or platform superuser
  * ``is_back_office_user`` — True for Admin, Staff, or platform superuser

Anonymous users get all-False so login/onboarding templates render safely.
"""
from __future__ import annotations

from .permissions import is_admin, is_back_office, is_staff_role


def user_role_flags(request) -> dict[str, bool]:
    """Exposes role flags to the template context for every authenticated request.

    Returns ``{'is_staff_role_user': bool, 'is_admin_user': bool,
    'is_back_office_user': bool}``. For anonymous users all values are
    ``False``.
    """
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return {
            'is_staff_role_user': False,
            'is_admin_user': False,
            'is_back_office_user': False,
        }
    return {
        'is_staff_role_user': is_staff_role(user),
        'is_admin_user': is_admin(user),
        'is_back_office_user': is_back_office(user),
    }
