"""Read-side selectors for the Analytics dashboard.

Selectors return the context dict consumed by ``dashboard.html``.
Views call these — they never hit the ORM directly.
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
_DEBT_AGE_WARNING_DAYS = 30
_DEBT_AGE_CRITICAL_DAYS = 45
_OUTSTANDING_DEBT_LIMIT = 8


def _fmt_peso(value: Decimal) -> str:
    """Return a Philippine-peso formatted string."""
    return f"₱{value:,.2f}"


def _sales_for_date(user: User, target: timezone.datetime.date) -> Decimal:
    """Return total_sales for a given date, or zero if no remittance exists."""
    rem = Remittance.objects.for_user(user).filter(date=target).first()
    return rem.total_sales if rem else Decimal("0.00")


def _sales_trend(user: User) -> tuple[Decimal, str, str]:
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


def _outstanding_debt(user: User) -> Decimal:
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


def _unreturned_containers(user: User) -> dict:
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


def _build_stats(user: User) -> list[dict]:
    """Assemble the asymmetric 6/3/3 summary cards."""
    today_sales, sales_trend, sales_direction = _sales_trend(user)
    containers = _unreturned_containers(user)
    outstanding = _outstanding_debt(user)

    return [
        {
            "key": "today_sales",
            "label": "Today's Total Sales",
            "value": _fmt_peso(today_sales),
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
            "value": _fmt_peso(outstanding),
            "raw_value": float(outstanding),
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


def _today_remittance(user: User) -> dict:
    """Centralized today's-remittance status for the dashboard panel.

    Returns one of three states:

      - ``none``      — no remittance exists for today.  CTA: create one.
      - ``draft``     — a staff member saved a draft for today.  CTA:
                        review/finalize the draft (links to the Add
                        Remittance page, which hydrates from the draft).
      - ``finalized`` — today's remittance is already finalized.

    The draft's ``created_by`` name is included so the admin can see at a
    glance who prepared it.
    """
    today = timezone.localdate()
    rem = (
        Remittance.objects.for_user(user)
        .filter(date=today)
        .select_related("created_by")
        .first()
    )

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


def _recent_remittances(user: User) -> list[dict]:
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


def _outstanding_debts(user: User) -> list[dict]:
    """All unpaid customer credit lines, ordered by age (oldest first)."""
    today = timezone.localdate()

    qs = (
        CreditLine.objects.for_user(user)
        .filter(qty_remaining__gt=0)
        .select_related("customer", "product")
        .order_by("created_at")[:_OUTSTANDING_DEBT_LIMIT]
    )

    rows: list[dict] = []
    for credit in qs:
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

        rows.append({
            "customer": customer_name,
            "customer_id": customer_id,
            "product": product_name,
            "qty_remaining": credit.qty_remaining,
            "amount": _fmt_peso(outstanding),
            "age_days": age,
            "issued_on": credit.created_at.strftime("%b %d, %Y"),
            "severity": severity,
        })
    return rows


# ---------------------------------------------------------------------------
# Public per-section selectors — used by the HTMX lazy-load partials so
# each section only runs its own queries instead of the full dashboard set.
# ---------------------------------------------------------------------------

def get_stats(user: User) -> list[dict]:
    """Stats row cards (6/3/3 grid)."""
    return _build_stats(user)


def get_recent_remittances(user: User) -> list[dict]:
    """Recent remittances table rows."""
    return _recent_remittances(user)


def get_outstanding_debts(user: User) -> list[dict]:
    """Outstanding debts table rows."""
    return _outstanding_debts(user)


def get_today_remittance(user: User) -> dict:
    """Today's remittance status for the dashboard side panel."""
    return _today_remittance(user)
