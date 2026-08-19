"""Presentation layer for the Analytics dashboard.

Transforms raw selector output (Decimals, querysets, model instances)
into template-ready dictionaries. All currency formatting, date
formatting, CSS class maps, label strings, and card-shaped dicts live
here — selectors stay focused on read-side queries.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from django.utils import timezone

from apps.remittance.models import Remittance

if TYPE_CHECKING:
    from apps.users.models import User

_DEBT_AGE_WARNING_DAYS = 30
_DEBT_AGE_CRITICAL_DAYS = 45


def fmt_peso(value: Decimal) -> str:
    """Return a Philippine-peso formatted string."""
    return f"₱{value:,.2f}"


def format_sales_trend(today_sales: Decimal, yesterday_sales: Decimal) -> tuple[str, str]:
    """Return (trend_text, direction) from today's and yesterday's sales.

    direction is "up", "down", or "flat".
    """
    if yesterday_sales == 0:
        return "No sales recorded yesterday", "flat"
    change = float(today_sales - yesterday_sales)
    pct = (change / float(yesterday_sales)) * 100
    if abs(pct) < 0.05:
        return "No change from yesterday", "flat"
    return f"{pct:+.1f}% from yesterday", "up" if pct > 0 else "down"


def build_container_breakdown(round_total: int, slim_total: int, other_total: int) -> dict:
    """Shape the container aggregate counts into a template-ready breakdown."""
    return {
        "total": round_total + slim_total + other_total,
        "breakdown": [
            {"label": "Round 8gal", "count": round_total},
            {"label": "Slim 8gal", "count": slim_total},
            {"label": "Other", "count": other_total},
        ],
    }


def build_stats_cards(
    *,
    today_sales: Decimal,
    sales_trend: str,
    sales_direction: str,
    outstanding_debt: Decimal,
    containers: dict,
) -> list[dict]:
    """Assemble the asymmetric 6/3/3 summary cards for the dashboard."""
    return [
        {
            "key": "today_sales",
            "label": "Today's Total Sales",
            "value": fmt_peso(today_sales),
            "raw_value": float(today_sales),
            "value_prefix": "₱",
            "value_decimals": 2,
            "value_size": "4xl",
            "trend": sales_trend,
            "trend_direction": sales_direction,
            "icon": "analytics",
            "accent": "primary",
            "col_span": "md:col-span-6",
        },
        {
            "key": "outstanding_debt",
            "label": "Outstanding Debt",
            "value": fmt_peso(outstanding_debt),
            "raw_value": float(outstanding_debt),
            "value_prefix": "₱",
            "value_decimals": 2,
            "value_size": "2xl",
            "subtitle": "Total Unpaid Credits",
            "icon": "dangerous",
            "accent": "error",
            "col_span": "md:col-span-3",
        },
        {
            "key": "unreturned_containers",
            "label": "Unreturned Containers",
            "value": str(containers["total"]),
            "raw_value": float(containers["total"]),
            "value_prefix": "",
            "value_decimals": 0,
            "subtitle": "Total Unreturned Containers",
            "value_size": "2xl",
            "icon": "water_damage",
            "accent": "tertiary",
            "col_span": "md:col-span-3",
        },
    ]


def build_today_remittance_status(rem: Remittance | None) -> dict:
    """Shape a Remittance (or None) into the dashboard side-panel status dict.

    Returns one of three states: ``none``, ``draft``, or ``finalized``.
    """
    if rem is None:
        return {
            "state": "none",
            "title": "No remittance for today yet",
            "message": "Operations are running but no financial data has been logged for this period.",
            "cta_text": "Create a Remittance",
            "cta_url": "remittance:add",
            "created_by": "",
        }

    creator = rem.created_by.full_name if rem.created_by else "—"

    if rem.status == Remittance.StatusChoices.DRAFT:
        return {
            "state": "draft",
            "title": "A draft remittance is ready for review",
            "message": f"A draft for today was prepared by {creator}. Review and finalize it when ready.",
            "cta_text": "Review Draft",
            "cta_url": "remittance:add",
            "created_by": creator,
        }

    return {
        "state": "finalized",
        "title": "Today's remittance is finalized",
        "message": "Today's financial data has been recorded and finalized.",
        "cta_text": "View Remittance",
        "cta_url": "remittance:history",
        "created_by": creator,
    }


def build_recent_remittance_row(rem: dict) -> dict:
    """Format a raw remittance values dict into a template-ready table row."""
    paid = rem["tithes_paid"] and rem["offering_paid"]
    return {
        "date": rem["date"].strftime("%b %d, %Y"),
        "total_sales": fmt_peso(rem["total_sales"]),
        "net_profit": fmt_peso(rem["net_profit"]),
        "tithes": fmt_peso(rem["tithe_amount"]),
        "tithes_status": "paid" if rem["tithes_paid"] else "unpaid",
        "has_warning": not paid,
    }


def build_outstanding_debt_row(credit: object, today: date) -> dict:
    """Format a CreditLine instance into a template-ready debt table row.

    The ``credit`` argument must have ``select_related`` on ``customer``
    and ``product`` already applied.
    """
    age = (today - credit.created_at.date()).days
    outstanding = credit.qty_remaining * credit.unit_price_snapshot
    if age >= _DEBT_AGE_CRITICAL_DAYS:
        severity = "critical"
    elif age >= _DEBT_AGE_WARNING_DAYS:
        severity = "warning"
    else:
        severity = "normal"

    customer_name = credit.customer.name if credit.customer else "Unknown"
    customer_id = f"HY-{credit.customer.pk:04d}" if credit.customer else ""
    product_name = credit.product.name if credit.product else "—"

    return {
        "customer": customer_name,
        "customer_id": customer_id,
        "product": product_name,
        "qty_remaining": credit.qty_remaining,
        "amount": fmt_peso(outstanding),
        "age_days": age,
        "issued_on": credit.created_at.strftime("%b %d, %Y"),
        "severity": severity,
    }


# ---------------------------------------------------------------------------
# Accent colour mapping for summary cards.
# Maps the `accent` key in a stat dict to the Tailwind classes used in the
# template (border-top colour + icon colour).
# ---------------------------------------------------------------------------
_ACCENT_CLASSES = {
    "primary": {"border": "border-t-primary", "icon": "text-primary"},
    "warning": {"border": "border-t-[#D97706]", "icon": "text-[#D97706]"},
    "error": {"border": "border-t-error", "icon": "text-error"},
    "tertiary": {"border": "border-t-tertiary", "icon": "text-tertiary"},
}


def apply_accent_classes(stats: list[dict]) -> None:
    """Pre-compute border_class / icon_class on each stat dict in-place."""
    for stat in stats:
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]
