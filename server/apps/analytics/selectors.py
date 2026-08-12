"""Read-side selectors for the Analytics dashboard.

Selectors return the context dict consumed by ``dashboard.html``.
Views call these — they never hit the ORM directly.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.customers.models import Customer
from apps.remittance.models import Remittance, RiderCredit

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)

_DASHBOARD_RECENT_LIMIT = 5
_LONG_DEBT_AGE_DAYS = 30
_CRITICAL_DEBT_AGE_DAYS = 45
_LONG_DEBT_LIMIT = 5


def _fmt_peso(value: Decimal) -> str:
    """Return a Philippine-peso formatted string."""
    return f"₱{value:,.2f}"


def _sales_for_date(user: "User", target: timezone.datetime.date) -> Decimal:
    """Return total_sales for a given date, or zero if no remittance exists."""
    rem = Remittance.objects.for_user(user).filter(date=target).first()
    return rem.total_sales if rem else Decimal("0.00")


def _sales_trend(user: "User") -> tuple[Decimal, str, str]:
    """Return today's sales, a human trend string, and the trend direction."""
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)

    today_sales = _sales_for_date(user, today)
    yesterday_sales = _sales_for_date(user, yesterday)

    if yesterday_sales == 0:
        trend = "No sales recorded yesterday"
        direction = "flat"
    else:
        change = float(today_sales - yesterday_sales)
        pct = (change / float(yesterday_sales)) * 100
        if abs(pct) < 0.05:
            trend = "No change from yesterday"
            direction = "flat"
        else:
            trend = f"{pct:+.1f}% from yesterday"
            direction = "up" if pct > 0 else "down"

    return today_sales, trend, direction


def _outstanding_debt(user: "User") -> Decimal:
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


def _unreturned_containers(user: "User") -> dict:
    """Return total and breakdown of customer-borrowed containers."""
    aggregates = (
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True)
        .aggregate(
            round=Coalesce(Sum("borrowed_round_8gal"), Value(0)),
            slim=Coalesce(Sum("borrowed_slim_8gal"), Value(0)),
            other=Coalesce(Sum("borrowed_other"), Value(0)),
        )
    )

    round_total = aggregates["round"] or 0
    slim_total = aggregates["slim"] or 0
    other_total = aggregates["other"] or 0
    total = round_total + slim_total + other_total

    return {
        "total": total,
        "breakdown": [
            {"label": "Round 8gal", "count": round_total},
            {"label": "Slim 8gal", "count": slim_total},
            {"label": "Other", "count": other_total},
        ],
    }


def _build_stats(user: "User") -> list[dict]:
    """Assemble the asymmetric 6/3/3 summary cards."""
    today_sales, sales_trend, sales_direction = _sales_trend(user)
    containers = _unreturned_containers(user)

    return [
        {
            "key": "today_sales",
            "label": "Today's Total Sales",
            "value": _fmt_peso(today_sales),
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
            "value": _fmt_peso(_outstanding_debt(user)),
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
            "value_size": "2xl",
            "icon": "water_damage",
            "accent": "tertiary",
            "col_span": "md:col-span-3",
        },
    ]


def _warning_banner(user: "User") -> dict:
    """Show a CTA when today's remittance has not yet been recorded."""
    today = timezone.localdate()
    has_today = Remittance.objects.for_user(user).filter(date=today).exists()

    return {
        "show": not has_today,
        "title": "No remittance for today yet",
        "message": "Operations are running but no financial data has been logged for this period.",
        "cta_text": "Create Today's Remittance",
    }


def _recent_remittances(user: "User") -> list[dict]:
    """Recent finalized/draft remittances for the dashboard table."""
    qs = (
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

    rows: list[dict] = []
    for rem in qs:
        paid = rem["tithes_paid"] and rem["offering_paid"]
        rows.append({
            "date": rem["date"].strftime("%b %d, %Y"),
            "total_sales": _fmt_peso(rem["total_sales"]),
            "net_profit": _fmt_peso(rem["net_profit"]),
            "tithes": _fmt_peso(rem["tithe_amount"]),
            "tithes_status": "paid" if rem["tithes_paid"] else "unpaid",
            "has_warning": not paid,
        })
    return rows


def _long_running_debts(user: "User") -> list[dict]:
    """Unpaid rider credits aged beyond the normal collection window."""
    today = timezone.localdate()
    threshold = today - timedelta(days=_LONG_DEBT_AGE_DAYS)

    qs = (
        RiderCredit.objects.for_user(user)
        .filter(is_repaid=False, created_at__date__lte=threshold)
        .select_related("customer", "rider")
        .order_by("created_at")[:_LONG_DEBT_LIMIT]
    )

    rows: list[dict] = []
    for credit in qs:
        age = (today - credit.created_at.date()).days
        outstanding = credit.amount - credit.total_repaid
        severity = "critical" if age >= _CRITICAL_DEBT_AGE_DAYS else "warning"

        customer_name = (
            credit.customer.name
            if credit.customer
            else (credit.recipient_name or "Unknown")
        )
        rider_name = credit.rider.full_name if credit.rider else "Unknown"

        # Display id (e.g. ``HY-0001``) for linking to the customer collect
        # modal. Only set when the credit is tied to a Customer record.
        customer_id = f"HY-{credit.customer.pk:04d}" if credit.customer else ""

        rows.append({
            "customer": customer_name,
            "customer_id": customer_id,
            "rider": rider_name,
            "amount": _fmt_peso(outstanding),
            "age_days": age,
            "issued_on": credit.created_at.strftime("%b %d, %Y"),
            "severity": severity,
        })
    return rows


def get_dashboard_context(user: "User") -> dict:
    """Build the full context for the main analytics dashboard."""
    logger.info("[%s] Built dashboard context", user.id)
    return {
        "today_date": timezone.localtime().strftime("%A, %b %d, %Y"),
        "warning_banner": _warning_banner(user),
        "stats": _build_stats(user),
        "recent_remittances": _recent_remittances(user),
        "long_running_debts": _long_running_debts(user),
        "ai_insights": [],
    }
