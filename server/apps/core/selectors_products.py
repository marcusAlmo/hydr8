"""Read-side selectors for the Products & Pricing page.

All functions are tenant-scoped via ``Product.objects.for_user(user)`` /
``User.objects.for_user(user)`` and return plain dicts in the exact shape
the ``products_pricing.html`` templates consume — so views can render
without any further transformation.

Layering: views call these selectors; selectors call the ORM (with
``select_related`` / ``prefetch_related`` to prevent N+1).  No business
logic lives here — only projection and formatting.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

from apps.core.models import Product
from apps.users.models import User, DriverCommission
from apps.users.presentation import initials as _initials, avatar_classes, driver_code

if TYPE_CHECKING:
    from apps.users.models import User as UserType


# --- UI token palettes ----------------------------------------------------
# Cycled deterministically by product index so the commission matrix header
# underlines stay visually distinct without persisting a colour per product.
_PRODUCT_BORDER_CLASSES: tuple[str, ...] = (
    "border-b-4 border-primary",
    "border-b-4 border-tertiary",
    "border-b-4 border-[#D97706]",
    "border-b-4 border-secondary",
    "border-b-4 border-outline",
    "border-b-4 border-outline-variant",
)


def _short_label(name: str, variation: str | None) -> str:
    """Builds a compact column label for the commission matrix header.

    Examples:
      ("Alkaline Water", "5-Gallon Round")   -> "Alkaline (5G)"
      ("Mineral Water", "5-Gallon Slim")     -> "Mineral (5G)"
      ("Pet Bottles", "350ml Case (24 Pcs)") -> "Pet Bottles (350ml)"
    """
    base = (name or "").split()[0].title() if name else "?"
    if not variation:
        return base
    # Pull the leading size token (e.g. "5-Gallon", "350ml", "1-Gallon").
    first_token = variation.split()[0] if variation else ""
    return f"{base} ({first_token})" if first_token else base


def list_products(user: "UserType") -> list[dict]:
    """Returns the product catalogue rows for the Products tab.

    Each row matches the shape consumed by ``product_table.html``:
      { id, name, variation, unit_price, is_active, is_default,
        row_class, name_class, action_activate }

    Soft-deleted products (``deleted_at__isnull=False``) are excluded.
    Inactive products (``deactivated_at__isnull=False``) are included
    so the admin can re-activate them.
    """
    qs = (
        Product.objects
        .for_user(user)
        .filter(deleted_at__isnull=True)
        .order_by("-is_default", "name", "variation")
    )

    rows: list[dict] = []
    for p in qs:
        is_active = p.deactivated_at is None
        rows.append({
            "id": p.id,
            "name": p.name,
            "variation": p.variation or "",
            "unit_price": f"{p.price:.2f}",
            "is_active": is_active,
            "is_default": p.is_default,
            # UI tokens — inactive rows are dimmed.
            "row_class": "" if is_active else "bg-surface-container-low/50",
            "name_class": "text-on-surface" if is_active else "text-on-surface-variant",
            # Inactive rows show the Activate action; active rows show Deactivate.
            "action_activate": not is_active,
        })
    return rows


def list_product_columns(user: "UserType") -> list[dict]:
    """Returns the product column headers for the commission matrix.

    Only active (non-deactivated, non-deleted) products are shown as
    columns — there is no point setting commission rates for products
    that cannot be sold.
    """
    qs = (
        Product.objects
        .for_user(user)
        .filter(deactivated_at__isnull=True, deleted_at__isnull=True)
        .order_by("-is_default", "name", "variation")
    )

    columns: list[dict] = []
    for idx, p in enumerate(qs):
        columns.append({
            "id": p.id,
            "label": _short_label(p.name, p.variation),
            "border_class": _PRODUCT_BORDER_CLASSES[idx % len(_PRODUCT_BORDER_CLASSES)],
        })
    return columns


def list_riders_with_rates(user: "UserType") -> list[dict]:
    """Returns the rider rows for the commission matrix, pre-aligned to
    the active product columns.

    Each row matches the shape consumed by ``commission_matrix.html``:
      { id, name, initials, avatar_bg, avatar_text, driver_code,
        rate_cells: [{ product_id, rate }] }

    ``rate_cells`` is pre-aligned with ``list_product_columns()`` so the
    template can iterate without a dict-key lookup (Django templates have
    no built-in ``|lookup`` filter).  Missing rates default to "0.00".
    """
    columns = list_product_columns(user)
    product_ids = [c["id"] for c in columns]

    # Drivers = users with the "driver" role, tenant-scoped, not soft-deleted.
    # User uses the default UserManager (not TenantManager), so we filter
    # by company_id manually.  Superusers (company_id=None) see all tenants.
    riders_qs = User.objects.filter(
        role__name__iexact="driver",
        deleted_at__isnull=True,
        is_active=True,
    )
    if not (user.is_superuser or user.company_id is None):
        riders_qs = riders_qs.filter(company_id=user.company_id)
    riders_qs = riders_qs.select_related('role').order_by("first_name", "last_name", "username")

    if not riders_qs or not product_ids:
        return []

    # Single query for all relevant commission rows — avoids N+1.
    rates_qs = (
        DriverCommission.objects
        .filter(driver__in=riders_qs, product_id__in=product_ids)
        .values("driver_id", "product_id", "rate_per_unit")
    )
    # Build a lookup: { (driver_id, product_id) -> rate_str }
    rate_map: dict[tuple, str] = {}
    for r in rates_qs:
        rate_map[(r["driver_id"], r["product_id"])] = f"{r['rate_per_unit']:.2f}"

    rows: list[dict] = []
    for rider in riders_qs:
        bg, txt = avatar_classes(rider)
        rows.append({
            "id": str(rider.pk),  # UUID → string for JS object key stability
            "name": rider.full_name,
            "initials": _initials(rider),
            "avatar_bg": bg,
            "avatar_text": txt,
            "driver_code": driver_code(rider),
            "rate_cells": [
                {
                    "product_id": pid,
                    "rate": rate_map.get((rider.pk, pid), "0.00"),
                }
                for pid in product_ids
            ],
        })
    return rows


def get_products_pricing_context(user: "UserType") -> dict:
    """Builds the full context dict for the ``products_pricing_view``.

    Centralises the assembly so the view stays thin.
    """
    products = list_products(user)
    columns = list_product_columns(user)
    riders = list_riders_with_rates(user)

    return {
        # --- Top bar ---
        "today_date": timezone.localtime().strftime("%A, %b %d, %Y"),

        # --- Tabs ---
        "tabs": [
            {"id": "products", "label": "Products", "icon": "inventory_2", "active": True},
            {"id": "commissions", "label": "Delivery Commissions", "icon": "payments", "active": False},
        ],

        # --- Products tab ---
        "products": products,
        "active_count": sum(1 for p in products if p["is_active"]),
        "default_count": sum(1 for p in products if p["is_default"]),
        "total_count": len(products),

        # --- Commissions tab ---
        "product_columns": columns,
        "page_size": 5,
        "rider_count": len(riders),
        "riders": riders,
    }
