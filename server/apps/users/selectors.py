"""Read-side selectors for the Users app.

Selectors keep views free of ORM calls and enforce tenant/RLS scoping.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from apps.users.models import Role, User
from apps.users.permissions import is_tenant_scoped

if TYPE_CHECKING:
    from apps.users.models import User as UserType


def get_user_by_id(request_user: UserType, user_id: str) -> User | None:
    """Returns an active user by UUID, scoped to the requester's tenant."""
    qs = User.objects.select_related('role', 'company').filter(
        deleted_at__isnull=True, pk=user_id
    )
    if is_tenant_scoped(request_user):
        qs = qs.filter(company_id=request_user.company_id)
    return qs.first()


def get_roles_for_user(request_user: UserType):
    """Returns active roles for the current tenant, ordered by name."""
    return Role.objects.for_user(request_user).active().select_related('company').order_by("name")


def username_exists(username: str, *, excluding_user_id: str | None = None) -> bool:
    """Returns True if an active (non-deleted) user already uses ``username``.

    Optionally excludes a user by UUID for edit flows.
    """
    qs = User.objects.filter(username=username, deleted_at__isnull=True)
    if excluding_user_id:
        qs = qs.exclude(pk=excluding_user_id)
    return qs.exists()
