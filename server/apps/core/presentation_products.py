"""Presentation layer for the Products & Pricing page.

Transforms Product model instances and raw commission rate data into
template-ready dicts. All label formatting, CSS class assignment, and
card/row shaping live here — selectors stay focused on tenant-scoped
queries.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.utils import timezone

from apps.users.presentation import initials as _initials, avatar_classes, driver_code

if TYPE_CHECKING:
    from apps.core.models import Product
    from apps.users.models import User

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


def short_label(name: str, variation: str | None) -> str:
    """Build a compact column label for the commission matrix header.

    Examples:
      ("Alkaline Water", "5-Gallon Round")   -> "Alkaline (5G)"
      ("Mineral Water", "5-Gallon Slim")     -> "Mineral (5G)"
      ("Pet Bottles", "350ml Case (24 Pcs)") -> "Pet Bottles (350ml)"
    """
    base = (name or "").split()[0].title() if name else "?"
    if not variation:
        return base
    first_token = variation.split()[0] if variation else ""
    return f"{base} ({first_token})" if first_token else base


def product_row(p: "Product") -> dict:
    """Shape a Product into the table row dict consumed by product_table.html."""
    is_active = p.deactivated_at is None
    return {
        "id": p.id,
        "name": p.name,
        "variation": p.variation or "",
        "unit_price": f"{Decimal(str(p.price)):.2f}",
        "is_active": is_active,
        "is_default": p.is_default,
        "row_class": "" if is_active else "bg-surface-container-low/50",
        "name_class": "text-on-surface" if is_active else "text-on-surface-variant",
        "action_activate": not is_active,
    }


def product_column(p: "Product", idx: int) -> dict:
    """Shape a Product into a commission matrix column header dict."""
    return {
        "id": p.id,
        "label": short_label(p.name, p.variation),
        "border_class": _PRODUCT_BORDER_CLASSES[idx % len(_PRODUCT_BORDER_CLASSES)],
    }


def rider_row(rider: "User", product_ids: list, rate_map: dict) -> dict:
    """Shape a rider User into a commission matrix row dict.

    ``rate_map`` is a dict of {(driver_id, product_id) -> rate_str}.
    Missing rates default to "0.00".
    """
    bg, txt = avatar_classes(rider)
    return {
        "id": str(rider.pk),
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
    }


def build_rate_map(rates_qs) -> dict:
    """Build a {(driver_id, product_id) -> rate_str} lookup from a values queryset."""
    return {
        (r["driver_id"], r["product_id"]): f"{r['rate_per_unit']:.2f}"
        for r in rates_qs
    }


def build_products_pricing_context(
    *,
    products: list[dict],
    columns: list[dict],
    riders: list[dict],
) -> dict:
    """Compose the full context dict for the products_pricing view."""
    return {
        "today_date": timezone.localtime().strftime("%A, %b %d, %Y"),
        "tabs": [
            {"id": "products", "label": "Products", "icon": "inventory_2", "active": True},
            {"id": "commissions", "label": "Delivery Commissions", "icon": "payments", "active": False},
        ],
        "products": products,
        "active_count": sum(1 for p in products if p["is_active"]),
        "default_count": sum(1 for p in products if p["is_default"]),
        "total_count": len(products),
        "product_columns": columns,
        "page_size": 5,
        "rider_count": len(riders),
        "riders": riders,
    }
