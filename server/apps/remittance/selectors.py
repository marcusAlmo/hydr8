"""Read-side selectors for the Remittance pages.

Selectors return dicts shaped for the ``add_remittance.html`` and
``remittance_history.html`` templates.  Views call these — they never hit
the ORM directly.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from django.db.models import Q, Sum

from apps.core.models import Product, SystemConfig
from apps.customers.models import CreditPayment, Customer
from apps.users.models import User, DriverCommission
from apps.users.presentation import avatar_classes, driver_code, initials
from .models import Remittance, RemittanceRiderProductLine

if TYPE_CHECKING:
    from apps.users.models import User as UserType

logger = logging.getLogger(__name__)


def _tithe_rate(company_id: int | None) -> float:
    """Returns the tenant-scoped tithe rate (fraction, e.g. 0.10)."""
    qs = SystemConfig.objects.filter(key="tithe_rate")
    row = qs.filter(company_id=company_id).first()
    if row is None:
        row = qs.filter(company_id__isnull=True).first()
    raw = row.value if row is not None else "0.10"
    try:
        return float(Decimal(raw))
    except (InvalidOperation, ValueError, TypeError):
        return 0.10


def list_products_for_remittance(user: "UserType") -> list[dict]:
    """Returns the active product catalogue in the shape the remittance
    form consumes.
    """
    qs = (
        Product.objects
        .for_user(user)
        .filter(deleted_at__isnull=True, deactivated_at__isnull=True)
        .order_by("name", "variation")
    )

    products: list[dict] = []
    for p in qs:
        name = p.name
        if p.variation:
            name = f"{name} - {p.variation}"
        products.append({
            "key": str(p.id),
            "name": name,
            "unit_price": float(p.price),
        })
    return products


def _active_riders_qs(user: "UserType"):
    """Tenant-scoped active driver users."""
    qs = User.objects.filter(
        role__name__iexact="driver",
        deleted_at__isnull=True,
        is_active=True,
    )
    if not (user.is_superuser or user.company_id is None):
        qs = qs.filter(company_id=user.company_id)
    return qs.order_by("first_name", "last_name", "username")


def _rider_repayments_for_date(
    user: "UserType",
    riders_qs,
    remittance_date: date,
) -> dict[str, list[dict]]:
    """Returns a mapping of ``rider_id -> [repayment_dict, ...]`` for
    CreditPayments collected on ``remittance_date`` that are attributed
    to an active rider (via ``CreditLine.care_of``) and not yet linked
    to a Remittance.

    Each repayment dict is shaped for the Alpine.js form::

        {"payer": str, "product_key": str, "qty": int, "amount": float}
    """
    rider_ids = [r.pk for r in riders_qs]
    if not rider_ids:
        return {}

    qs = (
        CreditPayment.objects
        .filter(
            company_id=getattr(user, "company_id", None),
            remittance__isnull=True,
            created_at__date=remittance_date,
            credit_line__care_of_id__in=rider_ids,
        )
        .select_related("credit_line__customer", "credit_line__product")
        .order_by("created_at")
    )

    by_rider: dict[str, list[dict]] = {}
    for cp in qs:
        rider_id = str(cp.credit_line.care_of_id)
        by_rider.setdefault(rider_id, []).append({
            "payer": cp.credit_line.customer.name,
            "product_key": str(cp.credit_line.product_id),
            "qty": cp.containers_paid,
            "amount": float(cp.amount),
        })
    return by_rider


def list_riders_for_remittance(
    user: "UserType",
    remittance_date: date | None = None,
) -> list[dict]:
    """Returns active riders with per-product commission rates, empty
    product lines, and auto-populated repayments, ready for Alpine.js
    to hydrate.

    ``remittance_date`` defaults to today.  Repayments are CreditPayments
    collected on that date, attributed to each rider via
    ``CreditLine.care_of``, and not yet linked to a Remittance.
    """
    remittance_date = remittance_date or date.today()
    products = list_products_for_remittance(user)
    product_keys = [p["key"] for p in products]
    riders_qs = _active_riders_qs(user)

    # Pre-fetch commission rates for (rider, product) pairs.
    rate_map: dict[tuple[str, str], float] = {}
    if riders_qs and product_keys:
        commissions = DriverCommission.objects.filter(
            driver__in=riders_qs,
            product_id__in=product_keys,
        ).values("driver_id", "product_id", "rate_per_unit")
        for row in commissions:
            rate_map[(str(row["driver_id"]), str(row["product_id"]))] = float(
                row["rate_per_unit"]
            )

    # Auto-populate repayments collected on the remittance date.
    repayments_by_rider = _rider_repayments_for_date(user, riders_qs, remittance_date)

    riders: list[dict] = []
    for idx, rider in enumerate(riders_qs):
        rider_id = str(rider.pk)
        commission_rates = {
            pk: rate_map.get((rider_id, pk), 0.0)
            for pk in product_keys
        }
        riders.append({
            "id": rider_id,
            "name": rider.full_name,
            "vehicle": "Rider",
            "plate": driver_code(rider),
            "selected": idx == 0,
            "commission_rates": commission_rates,
            "commission_override": "",
            "product_lines": [
                {
                    "product_key": pk,
                    "sold": 0,
                    "credited": 0,
                    "borrowed": 0,
                }
                for pk in product_keys
            ],
            "repayments": repayments_by_rider.get(rider_id, []),
        })
    return riders


def get_add_remittance_context(user: "UserType") -> dict:
    """Builds the full context for the Add Remittance page."""
    default_date = date.today()
    products = list_products_for_remittance(user)
    riders = list_riders_for_remittance(user, remittance_date=default_date)
    company_id = getattr(getattr(user, "company", None), "id", None)

    return {
        "today_date": datetime.now().strftime("%A, %b %d, %Y"),
        "default_date": default_date.isoformat(),
        "products": products,
        "riders": riders,
        "rider_position": f"1 of {len(riders)}" if riders else "0 of 0",
        "summary": {
            "total_sales": "₱0.00",
            "total_repayments": "₱0.00",
            "net_remittance": "₱0.00",
            "tithes": "₱0.00",
            "total_expenses": "₱0.00",
            "total_commission": "₱0.00",
            "manual_offering": "₱0.00",
        },
        "expenses": [],
        "tithe_rate": _tithe_rate(company_id),
        "offering_amount": "",
    }


def remittance_exists_for_date(user: "UserType", target_date: date) -> bool:
    """Returns True if a remittance already exists for the given date."""
    return Remittance.objects.for_user(user).filter(date=target_date).exists()


def remittance_status_for_date(user: "UserType", target_date: date) -> str | None:
    """Returns the status ('DRAFT' or 'FINALIZED') of a remittance for the
    given date, or ``None`` if no remittance exists.

    Used by the check-date endpoint so the Add Remittance form can
    distinguish between a draft (user can continue editing / re-save)
    and a finalized record (date is locked).
    """
    rem = (
        Remittance.objects
        .for_user(user)
        .filter(date=target_date)
        .only("status")
        .first()
    )
    return rem.status if rem else None


def _remittance_row(rem: Remittance) -> dict:
    """Builds the template-facing dict for a single remittance row.

    Shared by :func:`get_recent_remittances` (list page) and the
    ``update_paid_status`` HTMX endpoint (single-row swap) so both render
    identical markup.
    """
    creator = rem.created_by
    bg, txt = avatar_classes(creator)
    return {
        "id": rem.id,
        "date": rem.date.strftime("%Y-%m-%d"),
        "created_by": creator.full_name,
        "initials": initials(creator),
        "avatar_bg": bg,
        "avatar_text": txt,
        "total_sales": f"{rem.total_sales:,.2f}",
        "net_profit": f"{rem.net_profit:,.2f}",
        "tithes": f"{rem.tithe_amount:,.2f}",
        "tithes_paid": rem.tithes_paid,
        "offering_paid": rem.offering_paid,
        "unpaid": not (rem.tithes_paid and rem.offering_paid),
        "status": rem.status,
        "is_draft": rem.status == Remittance.StatusChoices.DRAFT,
    }


def get_recent_remittances(user: "UserType", limit: int = 25) -> dict:
    """Returns recent remittance rows and the total count for pagination."""
    qs = (
        Remittance.objects
        .for_user(user)
        .select_related("created_by")
        .order_by("-date")
    )

    rows: list[dict] = [_remittance_row(rem) for rem in qs[:limit]]
    return {"remittances": rows, "total": qs.count()}


def get_remittance_row(user: "UserType", remittance_id: int) -> dict | None:
    """Returns the template-facing dict for a single remittance, or
    ``None`` if it does not exist or is outside the user's tenant."""
    rem = (
        Remittance.objects
        .for_user(user)
        .select_related("created_by")
        .filter(id=remittance_id)
        .first()
    )
    return _remittance_row(rem) if rem else None


_RIDER_TREND_COLORS = [
    "#006591",
    "#505F76",
    "#35AF80",
    "#D97706",
    "#7C3AED",
    "#0EA5E9",
    "#E11D48",
    "#059669",
    "#4F46E5",
    "#EA580C",
    "#0D9488",
    "#B45309",
    "#F59E0B",
    "#6366F1",
    "#8B5CF6",
]


def _format_peso(value) -> str:
    """Format a Decimal/float as a Philippine peso string."""
    try:
        return f"₱{float(value):,.2f}"
    except (TypeError, ValueError):
        return "₱0.00"


def _rider_trend_color(index: int) -> str:
    return _RIDER_TREND_COLORS[index % len(_RIDER_TREND_COLORS)]


def get_remittance_history_context(user: "UserType", days: int = 30) -> dict:
    """Build the full page context for the Remittance History page from live DB data."""
    today = date.today()
    start = today - timedelta(days=days - 1)
    dates = [start + timedelta(days=i) for i in range(days)]
    labels = [d.strftime("%b %d") for d in dates]

    remit_rows = (
        Remittance.objects.for_user(user)
        .filter(date__range=(start, today))
        .values("date")
        .annotate(
            total_sales=Sum("total_sales"),
            total_commission=Sum("total_commission"),
        )
    )
    remit_by_date: dict[date, dict] = {row["date"]: row for row in remit_rows}

    total_sales: list[float] = []
    commissions_paid: list[float] = []
    for d in dates:
        rem = remit_by_date.get(d)
        total_sales.append(float(rem["total_sales"]) if rem and rem["total_sales"] is not None else 0.0)
        commissions_paid.append(float(rem["total_commission"]) if rem and rem["total_commission"] is not None else 0.0)

    # Outstanding debt — current customer ledger balance (no historical snapshots)
    current_debt = (
        Customer.objects.for_user(user)
        .filter(debt_balance__gt=0)
        .aggregate(Sum("debt_balance"))["debt_balance__sum"]
        or Decimal("0.00")
    )
    outstanding_debt = [float(current_debt)] * days

    # Per-rider units sold over the date range
    active_riders = list(_active_riders_qs(user))
    rider_ids = [r.pk for r in active_riders]

    unit_rows = (
        RemittanceRiderProductLine.objects.for_user(user)
        .filter(
            remittance_rider__remittance__date__range=(start, today),
            remittance_rider__rider_id__in=rider_ids,
        )
        .values(
            "remittance_rider__rider_id",
            "remittance_rider__remittance__date",
        )
        .annotate(total_sold=Sum("qty_sold"))
    )
    units_by_rider_date: dict[tuple[int, date], int] = {
        (row["remittance_rider__rider_id"], row["remittance_rider__remittance__date"]): row["total_sold"]
        for row in unit_rows
    }

    rider_series: list[dict] = []
    for idx, rider in enumerate(active_riders):
        units = [units_by_rider_date.get((rider.pk, d), 0) for d in dates]
        rider_series.append({
            "name": rider.full_name,
            "color": _rider_trend_color(idx),
            "units_sold": units,
        })

    trends = {
        "labels": labels,
        "total_sales": total_sales,
        "outstanding_debt": outstanding_debt,
        "commissions_paid": commissions_paid,
        "riders": rider_series,
    }

    # --- Summary cards -------------------------------------------------------
    mtd_start = date(today.year, today.month, 1)
    mtd_sales = (
        Remittance.objects.for_user(user)
        .filter(date__year=today.year, date__month=today.month)
        .aggregate(Sum("total_sales"))["total_sales__sum"]
        or Decimal("0.00")
    )

    prev_month = (mtd_start - timedelta(days=1)).replace(day=1)
    prev_sales = (
        Remittance.objects.for_user(user)
        .filter(date__year=prev_month.year, date__month=prev_month.month)
        .aggregate(Sum("total_sales"))["total_sales__sum"]
        or Decimal("0.00")
    )

    sales_change_pct = 0.0
    if prev_sales:
        sales_change_pct = round(float((mtd_sales - prev_sales) / prev_sales) * 100)

    unpaid_tithe = (
        Remittance.objects.for_user(user)
        .filter(tithes_paid=False)
        .aggregate(Sum("tithe_amount"))["tithe_amount__sum"]
        or Decimal("0.00")
    )
    unpaid_offering = (
        Remittance.objects.for_user(user)
        .filter(offering_paid=False)
        .aggregate(Sum("offering_amount"))["offering_amount__sum"]
        or Decimal("0.00")
    )
    unpaid_total = unpaid_tithe + unpaid_offering
    unpaid_count = Remittance.objects.for_user(user).filter(
        Q(tithes_paid=False) | Q(offering_paid=False)
    ).count()

    # AI Projected Profit (EOQ)
    quarter = (today.month - 1) // 3 + 1
    q_start_month = (quarter - 1) * 3 + 1
    q_end_month = q_start_month + 2
    q_start = date(today.year, q_start_month, 1)
    q_end = date(today.year, q_end_month, monthrange(today.year, q_end_month)[1])
    days_in_quarter = (q_end - q_start).days + 1
    days_elapsed = (today - q_start).days + 1
    qtd_net = (
        Remittance.objects.for_user(user)
        .filter(date__range=(q_start, today))
        .aggregate(Sum("net_profit"))["net_profit__sum"]
        or Decimal("0.00")
    )
    projected_eoq = Decimal("0.00")
    if days_elapsed > 0:
        projected_eoq = (qtd_net / days_elapsed) * days_in_quarter

    if sales_change_pct > 0:
        sales_badge_icon = "trending_up"
        sales_badge_color = "#10b981"
    elif sales_change_pct < 0:
        sales_badge_icon = "trending_down"
        sales_badge_color = "#ef4444"
    else:
        sales_badge_icon = "trending_flat"
        sales_badge_color = "#6b7280"

    summary_cards = [
        {
            "label": "Total Remittance (MTD)",
            "value": _format_peso(mtd_sales),
            "accent_bar": "#10b981" if sales_change_pct >= 0 else "#ef4444",
            "badge_text": f"{sales_change_pct:+.0f}%" if prev_sales else "New",
            "badge_icon": sales_badge_icon,
            "badge_color": sales_badge_color,
        },
        {
            "label": "Unpaid Tithes",
            "value": _format_peso(unpaid_total),
            "accent_bar": "#f59e0b",
            "badge_text": f"{unpaid_count} Items",
            "badge_icon": "warning",
            "badge_color": "text-error",
        },
        {
            "label": "AI Projected Profit (EOQ)",
            "value": _format_peso(projected_eoq),
            "accent_bar": "primary",
            "badge_text": "",
            "badge_icon": "auto_awesome",
            "badge_color": "text-primary",
            "shimmer": True,
        },
    ]

    # --- AI insight ----------------------------------------------------------
    direction = "increase" if sales_change_pct >= 0 else "decrease"
    total_month = Remittance.objects.for_user(user).filter(
        date__year=today.year, date__month=today.month
    )
    paid_month = total_month.filter(tithes_paid=True, offering_paid=True).count()
    total_month_count = total_month.count()
    compliance = 0.0
    if total_month_count:
        compliance = round((paid_month / total_month_count) * 100)

    ai_insight = (
        f'Hydr8 detected a <span class="text-tertiary font-bold">{sales_change_pct:+.0f}% {direction}</span> '
        f'in monthly sales compared to the previous month. Tithe and offering compliance is at '
        f'<span class="text-tertiary font-bold">{compliance:.0f}%</span>, with '
        f'<span class="text-tertiary font-bold">{_format_peso(unpaid_total)}</span> still unpaid. '
        f'At the current net-profit pace, the quarter is projected to close at '
        f'<span class="text-tertiary font-bold">{_format_peso(projected_eoq)}</span>.'
    )

    return {
        "today_date": datetime.now().strftime("%A, %b %d, %Y"),
        "trends": trends,
        "summary_cards": summary_cards,
        "ai_insight": ai_insight,
    }
