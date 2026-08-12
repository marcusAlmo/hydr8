"""Read-side selectors for the Users app.

Selectors keep views free of ORM calls and enforce tenant/RLS scoping.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from apps.users.models import Role, User

if TYPE_CHECKING:
    from apps.users.models import User as UserType


def get_user_by_id(request_user: "UserType", user_id: str) -> User | None:
    """Returns an active user by UUID, scoped to the requester's tenant."""
    qs = User.objects.filter(deleted_at__isnull=True, pk=user_id)
    if not request_user.is_superuser and request_user.company_id is not None:
        qs = qs.filter(company_id=request_user.company_id)
    return qs.first()


def get_roles_for_user(request_user: "UserType"):
    """Returns active roles for the current tenant, ordered by name."""
    return Role.objects.for_user(request_user).active().select_related('company').order_by("name")
