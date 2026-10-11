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


def _yesterday_ai_insight(user: User) -> dict:
    """Compute daily operational health metrics and status indicators for yesterday."""
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    yesterday_str = yesterday.strftime("%A, %b %d, %Y")
    short_date = yesterday.strftime("%b %d")

    rem = (
        Remittance.objects.for_user(user)
        .filter(date=yesterday)
        .select_related("created_by")
        .first()
    )

    if rem is None:
        return {
            "date": yesterday,
            "date_str": yesterday_str,
            "short_date": short_date,
            "mood": "warning",
            "mood_label": "Attention Needed",
            "header_gradient": "bg-[#D97706]",
            "pill_class": "bg-[#D97706]/15 text-[#D97706]",
            "banner_class": "bg-[#D97706]/10 border-[#D97706]/30 text-[#D97706]",
            "icon": "warning",
            "title": "Missing Operational Remittance",
            "sample_text": (
                "No remittance was logged for yesterday. Operations ran without "
                "closing the daily register, which can cause debt and container discrepancies."
            ),
            "metrics": {
                "sales": "₱0.00",
                "net_profit": "₱0.00",
                "tithes_status": "Unrecorded",
                "remittance_status": "Missing",
            },
            "detailed_insights": [
                {
                    "category": "Revenue & Margins",
                    "icon": "payments",
                    "content": "No sales transactions were closed or verified for yesterday. Ensure staff record any carried-over cash.",
                },
                {
                    "category": "Credit & Collections",
                    "icon": "account_balance_wallet",
                    "content": "Customer payments and borrowed containers recorded yesterday are unassociated with a finalized batch.",
                },
                {
                    "category": "Station Inventory",
                    "icon": "water_drop",
                    "content": "Water volume and 5-gallon container movements require sign-off to maintain accurate station balances.",
                },
            ],
            "recommendations": [
                "Log and finalize yesterday's remittance sheet before concluding today's sales.",
                "Conduct a physical count of round and slim containers in stock.",
                "Verify rider cash turn-overs from yesterday with the on-duty staff.",
            ],
            "action_url": "remittance:add",
            "action_label": "Create Remittance",
        }

    creator = rem.created_by.full_name if rem.created_by else "Staff"
    sales_fmt = _fmt_peso(rem.total_sales)
    profit_fmt = _fmt_peso(rem.net_profit)
    tithes_paid = rem.tithes_paid and rem.offering_paid
    tithe_status_label = "Paid" if tithes_paid else "Unpaid"

    if rem.status == Remittance.StatusChoices.DRAFT:
        return {
            "date": yesterday,
            "date_str": yesterday_str,
            "short_date": short_date,
            "mood": "warning",
            "mood_label": "Draft Pending",
            "header_gradient": "bg-[#D97706]",
            "pill_class": "bg-[#D97706]/15 text-[#D97706]",
            "banner_class": "bg-[#D97706]/10 border-[#D97706]/30 text-[#D97706]",
            "icon": "edit_note",
            "title": "Yesterday's Draft Awaiting Finalization",
            "sample_text": (
                f"Yesterday's remittance was prepared by {creator} with {sales_fmt} in sales, "
                "but remains in draft state. Review and finalize it to officially close the period."
            ),
            "metrics": {
                "sales": sales_fmt,
                "net_profit": profit_fmt,
                "tithes_status": tithe_status_label,
                "remittance_status": "Draft",
            },
            "detailed_insights": [
                {
                    "category": "Revenue Verification",
                    "icon": "payments",
                    "content": f"A draft total of {sales_fmt} is awaiting manager PIN sign-off.",
                },
                {
                    "category": "Driver Commissions",
                    "icon": "local_shipping",
                    "content": "Driver delivery credits and expense deductions are logged but not yet frozen.",
                },
                {
                    "category": "Audit Compliance",
                    "icon": "verified_user",
                    "content": "Finalizing locks child expense and credit entries against accidental edits.",
                },
            ],
            "recommendations": [
                "Review expense line items and rider commissions recorded in the draft.",
                "Authenticate with Admin PIN to complete the finalization workflow.",
            ],
            "action_url": "remittance:add",
            "action_label": "Review & Finalize",
        }

    if not tithes_paid:
        return {
            "date": yesterday,
            "date_str": yesterday_str,
            "short_date": short_date,
            "mood": "warning",
            "mood_label": "Attention Needed",
            "header_gradient": "bg-[#D97706]",
            "pill_class": "bg-[#D97706]/15 text-[#D97706]",
            "banner_class": "bg-[#D97706]/10 border-[#D97706]/30 text-[#D97706]",
            "icon": "priority_high",
            "title": "Unsettled Tithes from Yesterday",
            "sample_text": (
                f"Yesterday closed with {sales_fmt} in sales, but {_fmt_peso(rem.tithe_amount)} "
                "in tithe contributions remains unpaid. Settle outstanding commitments."
            ),
            "metrics": {
                "sales": sales_fmt,
                "net_profit": profit_fmt,
                "tithes_status": "Unpaid",
                "remittance_status": "Finalized",
            },
            "detailed_insights": [
                {
                    "category": "Tithe Compliance",
                    "icon": "volunteer_activism",
                    "content": f"Calculated tithe allocation of {_fmt_peso(rem.tithe_amount)} has not been marked as paid.",
                },
                {
                    "category": "Operating Cashflow",
                    "icon": "payments",
                    "content": f"Net cash on hand reflects {profit_fmt} prior to tithe disbursement.",
                },
                {
                    "category": "Reconciliation",
                    "icon": "account_balance",
                    "content": "Verify physical cashier envelopes before marking contributions as settled.",
                },
            ],
            "recommendations": [
                f"Disburse church tithe allocation ({_fmt_peso(rem.tithe_amount)}) from yesterday's collection.",
                "Check that offering envelopes match physical register receipts.",
            ],
            "action_url": "remittance:history",
            "action_label": "View History",
        }

    if rem.net_profit < 0:
        return {
            "date": yesterday,
            "date_str": yesterday_str,
            "short_date": short_date,
            "mood": "warning",
            "mood_label": "Deficit Warning",
            "header_gradient": "bg-[#BA1A1A]",
            "pill_class": "bg-[#BA1A1A]/15 text-[#BA1A1A]",
            "banner_class": "bg-[#BA1A1A]/10 border-[#BA1A1A]/30 text-[#BA1A1A]",
            "icon": "trending_down",
            "title": "Operating Deficit Incurred",
            "sample_text": (
                f"Yesterday expenses outpaced revenue, resulting in a net deficit of {profit_fmt}. "
                "Review emergency equipment maintenance and fuel expense spikes."
            ),
            "metrics": {
                "sales": sales_fmt,
                "net_profit": profit_fmt,
                "tithes_status": tithe_status_label,
                "remittance_status": "Finalized",
            },
            "detailed_insights": [
                {
                    "category": "Expense Analysis",
                    "icon": "receipt_long",
                    "content": "Total operating expenditures exceeded daily gross refill revenue.",
                },
                {
                    "category": "Margin Impact",
                    "icon": "trending_down",
                    "content": "Fixed and variable overhead consumed operational reserves for the day.",
                },
                {
                    "category": "Recovery Strategy",
                    "icon": "lightbulb",
                    "content": "Boost high-margin alkaline sales to offset yesterday's deficit.",
                },
            ],
            "recommendations": [
                "Audit yesterday's individual expense receipts for non-routine line items.",
                "Tighten driver fuel allowances and inspect vehicle efficiency.",
            ],
            "action_url": "remittance:history",
            "action_label": "Inspect Remittance",
        }

    if rem.total_sales > Decimal("0.00") and rem.net_profit > Decimal("0.00"):
        margin_pct = (rem.net_profit / rem.total_sales) * 100
        if margin_pct >= 40:
            return {
                "date": yesterday,
                "date_str": yesterday_str,
                "short_date": short_date,
                "mood": "positive",
                "mood_label": "Positive Health",
                "header_gradient": "bg-tertiary",
                "pill_class": "bg-tertiary/15 text-tertiary",
                "banner_class": "bg-tertiary/10 border-tertiary/30 text-tertiary",
                "icon": "trending_up",
                "title": "Strong Operational Margins",
                "sample_text": (
                    f"Yesterday delivered excellent operating performance: {sales_fmt} in sales with a {margin_pct:.0f}% "
                    f"net margin ({profit_fmt}). Tithes and obligations were fully cleared."
                ),
                "metrics": {
                    "sales": sales_fmt,
                    "net_profit": profit_fmt,
                    "tithes_status": "Paid",
                    "remittance_status": "Finalized",
                },
                "detailed_insights": [
                    {
                        "category": "Profit Margin",
                        "icon": "trending_up",
                        "content": f"Healthy net profit ratio of {margin_pct:.1f}% achieved across all delivery routes.",
                    },
                    {
                        "category": "Collection Health",
                        "icon": "payments",
                        "content": "Strong cash turn-over with minimal non-credit slippage recorded.",
                    },
                    {
                        "category": "Logistics Flow",
                        "icon": "local_shipping",
                        "content": "Dispatch volumes met station targets with timely customer bottle returns.",
                    },
                ],
                "recommendations": [
                    "Maintain current driver route allocations for optimal delivery times.",
                    "Pre-stage cleaned bottle buffers for tomorrow's commercial refills.",
                ],
                "action_url": "remittance:history",
                "action_label": "View Remittance",
            }

    # Neutral / baseline state
    return {
        "date": yesterday,
        "date_str": yesterday_str,
        "short_date": short_date,
        "mood": "neutral",
        "mood_label": "Stable Baseline",
        "header_gradient": "bg-primary",
        "pill_class": "bg-primary/15 text-primary",
        "banner_class": "bg-primary/10 border-primary/30 text-primary",
        "icon": "insights",
        "title": "Steady Daily Operations",
        "sample_text": (
            f"Yesterday ran at normal operating levels: {sales_fmt} in gross sales and {profit_fmt} "
            "net profit. Key operational indicators remained stable."
        ),
        "metrics": {
            "sales": sales_fmt,
            "net_profit": profit_fmt,
            "tithes_status": tithe_status_label,
            "remittance_status": "Finalized" if rem.status == Remittance.StatusChoices.FINALIZED else rem.status.capitalize(),
        },
        "detailed_insights": [
            {
                "category": "Throughput Velocity",
                "icon": "speed",
                "content": "Volume demand matched expected daily distribution patterns.",
            },
            {
                "category": "Cost Discipline",
                "icon": "savings",
                "content": "Standard operational expenses remained within budget thresholds.",
            },
            {
                "category": "Customer Activity",
                "icon": "groups",
                "content": "Regular refilling cycles recorded with balanced bottle exchanges.",
            },
        ],
        "recommendations": [
            "Monitor container return turn-around times among store accounts.",
            "Promote 5-gallon package bundles to boost average transaction value.",
        ],
        "action_url": "remittance:history",
        "action_label": "View History",
    }


def get_yesterday_ai_insight(user: User) -> dict:
    """Return yesterday's operational status indicators and diagnostic metrics."""
    return _yesterday_ai_insight(user)
