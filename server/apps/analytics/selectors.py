"""Read-side selectors for the Analytics dashboard.

Selectors return raw data — Decimals, querysets, model instances, and
simple aggregates. All template-shaped formatting (currency strings,
CSS classes, card dicts, table rows) lives in ``presentation.py``.
Views compose selectors with presentation functions.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.customers.models import CreditLine, Customer
from apps.remittance.models import Remittance

if TYPE_CHECKING:
    from apps.users.models import User

_DASHBOARD_RECENT_LIMIT = 8
_OUTSTANDING_DEBT_LIMIT = 8


def get_today_sales(user: "User") -> Decimal:
    """Return total_sales for today, or zero if no remittance exists."""
    today = timezone.localdate()
    rem = Remittance.objects.for_user(user).filter(date=today).first()
    return rem.total_sales if rem else Decimal("0.00")


def get_yesterday_sales(user: "User") -> Decimal:
    """Return total_sales for yesterday, or zero if no remittance exists."""
    yesterday = timezone.localdate() - timedelta(days=1)
    rem = Remittance.objects.for_user(user).filter(date=yesterday).first()
    return rem.total_sales if rem else Decimal("0.00")


def get_outstanding_debt(user: "User") -> Decimal:
    """Sum of outstanding customer debt balances."""
    result = (
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True)
        .aggregate(
            total=Coalesce(
                Sum("debt_balance"),
                Value(Decimal("0.00")),
            )
        )
    )
    return result["total"] or Decimal("0.00")


def get_unreturned_container_counts(user: "User") -> dict[str, int]:
    """Return per-type counts of customer-borrowed containers."""
    aggregates = (
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True)
        .aggregate(
            round=Coalesce(Sum("borrowed_round_8gal"), Value(0)),
            slim=Coalesce(Sum("borrowed_slim_8gal"), Value(0)),
            other=Coalesce(Sum("borrowed_other"), Value(0)),
        )
    )
    return {
        "round": aggregates["round"] or 0,
        "slim": aggregates["slim"] or 0,
        "other": aggregates["other"] or 0,
    }


def get_today_remittance(user: "User") -> Remittance | None:
    """Return today's Remittance (draft or finalized), or None."""
    today = timezone.localdate()
    return (
        Remittance.objects.for_user(user)
        .filter(date=today)
        .select_related("created_by")
        .first()
    )


def get_recent_remittances(user: "User") -> list[dict]:
    """Return raw values dicts for the most recent remittances.

    Each dict contains the raw DB values needed by the presentation
    layer — no formatting is applied here.
    """
    return list(
        Remittance.objects.for_user(user)
        .order_by("-date")
        .values(
            "date",
            "total_sales",
            "net_profit",
            "tithe_amount",
            "tithes_paid",
            "offering_paid",
        )[:_DASHBOARD_RECENT_LIMIT]
    )


def get_outstanding_debt_credits(user: "User") -> list[CreditLine]:
    """Return unpaid customer credit lines, ordered by age (oldest first).

    ``select_related`` on ``customer`` and ``product`` is applied so the
    presentation layer can access them without additional queries.
    """
    return list(
        CreditLine.objects.for_user(user)
        .filter(qty_remaining__gt=0)
        .select_related("customer", "product")
        .order_by("created_at")[:_OUTSTANDING_DEBT_LIMIT]
    )
