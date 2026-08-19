"""Read-side selectors for the Products & Pricing page.

Selectors return raw data — Product querysets, rider querysets, and
raw commission rate values. All template-shaped formatting (label
strings, CSS classes, row/column dicts) lives in
``presentation_products.py``. Views compose selectors with presentation
functions.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from apps.core.models import Product
from apps.users.models import User, DriverCommission

if TYPE_CHECKING:
    from apps.users.models import User as UserType


def list_products(user: "UserType") -> list[Product]:
    """Return the product catalogue for the Products tab.

    Soft-deleted products are excluded. Inactive products (deactivated)
    are included so the admin can re-activate them.
    """
    return list(
        Product.objects
        .for_user(user)
        .filter(deleted_at__isnull=True)
        .order_by("-is_default", "name", "variation")
    )


def list_active_products(user: "UserType") -> list[Product]:
    """Return active (non-deactivated, non-deleted) products for commission columns."""
    return list(
        Product.objects
        .for_user(user)
        .filter(deactivated_at__isnull=True, deleted_at__isnull=True)
        .order_by("-is_default", "name", "variation")
    )


def list_riders(user: "UserType") -> list[User]:
    """Return tenant-scoped active drivers for the commission matrix.

    User uses the default UserManager (not TenantManager), so we filter
    by company_id manually. Superusers (company_id=None) see all tenants.
    """
    riders_qs = User.objects.filter(
        role__name__iexact="driver",
        deleted_at__isnull=True,
        is_active=True,
    )
    if not (user.is_superuser or user.company_id is None):
        riders_qs = riders_qs.filter(company_id=user.company_id)
    return list(
        riders_qs.select_related('role').order_by("first_name", "last_name", "username")
    )


def get_commission_rates(riders: list, product_ids: list) -> list[dict]:
    """Return raw commission rate values for the given riders and products.

    Returns a list of dicts with keys: driver_id, product_id, rate_per_unit.
    """
    if not riders or not product_ids:
        return []
    return list(
        DriverCommission.objects
        .filter(driver__in=riders, product_id__in=product_ids)
        .values("driver_id", "product_id", "rate_per_unit")
    )
