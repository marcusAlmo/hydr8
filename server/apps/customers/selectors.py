"""Read-side selectors for the Customers pages.

Selectors return dicts shaped for ``customer_list.html`` and its
partials.  Views call these — they never hit the ORM directly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from apps.core.models import Product
from apps.users.presentation import driver_code as user_driver_code
from apps.users.presentation import initials as user_initials

from .models import Customer, CreditLine, CreditPayment

if TYPE_CHECKING:
    from apps.users.models import User as UserType

logger = logging.getLogger(__name__)

_CUSTOMER_DISPLAY_PREFIX = "HY"

# ---------------------------------------------------------------------------
# Sort mapping for the customer table HTMX partial.
# ---------------------------------------------------------------------------
SORT_FIELD_MAP: dict[str, str] = {
    "name": "name",
    "debt_balance": "debt_balance_raw",
    "borrowed_total": "borrowed_total",
    "payable_amount": "payable_amount_raw",
    "last_credit": "last_credit_days",
}
DEFAULT_SORT = "name"
DEFAULT_DIR = "asc"


def _display_id(customer: Customer) -> str:
    """Human-readable customer code, e.g. ``HY-0001``."""
    return f"{_CUSTOMER_DISPLAY_PREFIX}-{customer.pk:04d}"


def _parse_display_id(customer_id: str) -> int | None:
    """Parses a display id (``HY-XXXX`` or plain int) back to a primary key."""
    raw = customer_id
    if raw.startswith(_CUSTOMER_DISPLAY_PREFIX + "-"):
        raw = raw.split("-", 1)[1]
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _customer_initials(name: str) -> str:
    """Returns a 2-character initial string from a customer name."""
    name = (name or "").strip()
    if not name:
        return "?"
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()
    return parts[0][:2].upper()


def _format_peso(value) -> str:
    """Format a Decimal/float as a Philippine peso string."""
    try:
        return f"₱{float(value):,.2f}"
    except (TypeError, ValueError):
        return "₱0.00"


def _days_since(dt) -> int:
    """Days elapsed since ``dt``; 9999 means no date was provided."""
    if not dt:
        return 9999
    now = timezone.now()
    if dt > now:
        return 0
    return (now - dt).days


def _days_ago(dt) -> str:
    """Human-friendly relative time string."""
    days = _days_since(dt)
    if days == 9999:
        return "Never"
    if days == 0:
        return "Today"
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


def _customer_borrowed_total(customer: Customer) -> int:
    """Total unreturned containers for a customer."""
    return (
        customer.borrowed_round_8gal
        + customer.borrowed_slim_8gal
        + customer.borrowed_other
    )


def _customer_row_border(status: str) -> str:
    return {
        Customer.Status.ACTIVE: "border-l-transparent",
        Customer.Status.FLAGGED: "border-l-[#D97706]",
        Customer.Status.BLACKLISTED: "border-l-error",
    }.get(status, "border-l-transparent")


def _customer_anomaly_badge(status: str) -> str:
    if status == Customer.Status.ACTIVE:
        return ""
    return status.upper()


def _customer_status_badge_class(status: str) -> str:
    return {
        Customer.Status.ACTIVE: "bg-tertiary-container/30 text-tertiary border-tertiary/30",
        Customer.Status.FLAGGED: "bg-[#D97706]/15 text-[#D97706] border-[#D97706]/30",
        Customer.Status.BLACKLISTED: "bg-error/10 text-error border-error/30",
    }.get(status, "bg-tertiary-container/30 text-tertiary border-tertiary/30")


def _customer_status_label(status: str) -> str:
    return {
        Customer.Status.ACTIVE: "Active",
        Customer.Status.FLAGGED: "Flagged",
        Customer.Status.BLACKLISTED: "Blacklisted",
    }.get(status, status.title())


def _customer_row(customer: Customer) -> dict:
    """Converts a ``Customer`` into the table/detail row shape."""
    debt = customer.debt_balance
    borrowed_total = _customer_borrowed_total(customer)
    has_debt = debt > 0
    status = customer.status
    return {
        "id": _display_id(customer),
        "pk": customer.pk,
        "name": customer.name,
        "initials": _customer_initials(customer.name),
        "address": customer.address or "",
        "contact_number": customer.contact_number or "",
        "debt_balance": _format_peso(debt),
        "debt_balance_raw": float(debt),
        "debt_class": "text-error" if has_debt else "text-tertiary",
        "borrowed_round_8gal": customer.borrowed_round_8gal,
        "borrowed_slim_8gal": customer.borrowed_slim_8gal,
        "borrowed_other": customer.borrowed_other,
        "borrowed_total": borrowed_total,
        "borrowed_class": "text-on-surface-variant",
        "payable_amount": _format_peso(debt),
        "payable_amount_raw": float(debt),
        "last_credit_at": _days_ago(customer.last_credit_at),
        "last_credit_days": _days_since(customer.last_credit_at),
        "row_border": _customer_row_border(status),
        "has_debt": has_debt,
        "status": status,
        "anomaly_badge": _customer_anomaly_badge(status),
        "anomaly_reason": customer.flagged_reason or "",
        "credit_limit": (
            _format_peso(customer.credit_limit)
            if customer.credit_limit and customer.credit_limit > 0
            else "Not set"
        ),
    }


def _debt_row(customer: Customer) -> dict:
    """Converts a ``Customer`` into the debt-management row shape."""
    days_overdue = _days_since(customer.last_credit_at)
    last_payment = _last_payment_dt(customer)
    last_payment_at = _days_ago(last_payment)

    if customer.status == Customer.Status.BLACKLISTED or days_overdue > 90:
        suggested_action = "Send final demand"
        action_class = "bg-error text-on-primary"
    elif days_overdue > 7 or customer.status == Customer.Status.FLAGGED:
        suggested_action = "Call to collect"
        action_class = "bg-primary text-on-primary"
    else:
        suggested_action = "Monitor"
        action_class = "bg-surface-container text-on-surface-variant"

    if days_overdue > 30:
        days_class = "text-error"
    elif days_overdue > 7:
        days_class = "text-[#D97706]"
    else:
        days_class = "text-on-surface-variant"

    if not last_payment or _days_since(last_payment) > 30:
        last_payment_class = "text-error"
    elif _days_since(last_payment) > 7:
        last_payment_class = "text-[#D97706]"
    else:
        last_payment_class = "text-on-surface-variant"

    return {
        "id": _display_id(customer),
        "name": customer.name,
        "initials": _customer_initials(customer.name),
        "debt_balance": _format_peso(customer.debt_balance),
        "days_overdue": days_overdue,
        "days_overdue_class": days_class,
        "last_payment_at": last_payment_at,
        "last_payment_class": last_payment_class,
        "suggested_action": suggested_action,
        "action_class": action_class,
        "status": customer.status,
        "anomaly_badge": _customer_anomaly_badge(customer.status),
    }


def _last_payment_dt(customer: Customer) -> datetime | None:
    payment = (
        CreditPayment.objects.filter(credit_line__customer=customer)
        .order_by("-created_at")
        .first()
    )
    return payment.created_at if payment else None


def _pagination(current_page: int, total: int) -> dict:
    return {
        "showing_from": 1 if total else 0,
        "showing_to": total,
        "total": total,
        "total_display": f"{total:,}",
        "current_page": current_page,
        "total_pages": 1 if total else 1,
    }


def _customer_filters(user: "UserType") -> list[dict]:
    base = Customer.objects.for_user(user).filter(deleted_at__isnull=True)
    return [
        {
            "label": "All",
            "count": base.count(),
            "active": True,
        },
        {
            "label": "Has Debt",
            "count": base.filter(debt_balance__gt=0).count(),
            "active": False,
        },
        {
            "label": "Has Borrowed Items",
            "count": base.filter(
                Q(borrowed_round_8gal__gt=0)
                | Q(borrowed_slim_8gal__gt=0)
                | Q(borrowed_other__gt=0)
            ).count(),
            "active": False,
        },
        {
            "label": "Anomalous",
            "count": base.filter(
                status__in=(Customer.Status.FLAGGED, Customer.Status.BLACKLISTED)
            ).count(),
            "active": False,
        },
    ]


def _customer_stats(user: "UserType") -> list[dict]:
    base = Customer.objects.for_user(user).filter(deleted_at__isnull=True)
    total = base.count()
    debtor_count = base.filter(debt_balance__gt=0).count()
    total_debt = (
        base.filter(debt_balance__gt=0).aggregate(Sum("debt_balance"))[
            "debt_balance__sum"
        ]
        or Decimal("0.00")
    )
    borrowed_total = (
        base.aggregate(
            total=Sum(
                F("borrowed_round_8gal")
                + F("borrowed_slim_8gal")
                + F("borrowed_other")
            )
        )["total"]
        or 0
    )
    borrowed_count = base.filter(
        Q(borrowed_round_8gal__gt=0)
        | Q(borrowed_slim_8gal__gt=0)
        | Q(borrowed_other__gt=0)
    ).count()
    return [
        {
            "key": "total_customers",
            "label": "Total Customers",
            "value": f"{total:,}",
            "value_size": "4xl",
            "subtitle": "Active accounts",
            "icon": "group",
            "accent": "primary",
            "col_span": "md:col-span-4",
        },
        {
            "key": "total_debt",
            "label": "Total Outstanding Debt",
            "value": _format_peso(total_debt),
            "value_size": "3xl",
            "subtitle": f"{debtor_count} active debtors",
            "icon": "dangerous",
            "accent": "error",
            "col_span": "md:col-span-4",
        },
        {
            "key": "pending_containers",
            "label": "Unreturned Containers",
            "value": f"{borrowed_total:,}",
            "value_size": "4xl",
            "subtitle": f"Across {borrowed_count} customers",
            "icon": "water_damage",
            "accent": "warning",
            "col_span": "md:col-span-4",
        },
    ]


def _debt_stats_and_rows(user: "UserType") -> tuple[list[dict], list[dict]]:
    debtors = (
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True, debt_balance__gt=0)
        .order_by("-debt_balance")
    )
    debtor_count = debtors.count()
    total_debt = (
        debtors.aggregate(Sum("debt_balance"))["debt_balance__sum"]
        or Decimal("0.00")
    )

    rows = [_debt_row(c) for c in debtors]
    overdue_30_count = sum(1 for r in rows if r["days_overdue"] > 30)
    overdue_30_amount = sum(
        c.debt_balance for c in debtors if _days_since(c.last_credit_at) > 30
    )
    avg_days = (
        round(sum(r["days_overdue"] for r in rows) / debtor_count)
        if debtor_count
        else 0
    )

    stats = [
        {
            "key": "total_debt",
            "label": "Total Outstanding",
            "value": _format_peso(total_debt),
            "value_size": "3xl",
            "subtitle": f"Across {debtor_count} debtors",
            "icon": "dangerous",
            "accent": "error",
            "col_span": "md:col-span-6",
        },
        {
            "key": "overdue_30",
            "label": "Overdue 30+ Days",
            "value": str(overdue_30_count),
            "value_size": "4xl",
            "subtitle": _format_peso(overdue_30_amount) + " at risk",
            "icon": "schedule",
            "accent": "warning",
            "col_span": "md:col-span-3",
        },
        {
            "key": "avg_days_overdue",
            "label": "Avg Days Overdue",
            "value": str(avg_days),
            "value_size": "4xl",
            "subtitle": "Across active debtors",
            "icon": "hourglass_top",
            "accent": "warning",
            "col_span": "md:col-span-3",
        },
    ]
    return stats, rows


def _ranking_context(user: "UserType") -> dict:
    top_payers_qs = (
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True, credit_lines__payments__isnull=False)
        .annotate(
            total_paid=Sum("credit_lines__payments__amount"),
            payment_count=Count("credit_lines__payments"),
        )
        .order_by("-total_paid")[:5]
    )
    top_payers: list[dict] = []
    rank_class_map = {
        1: "bg-tertiary text-on-primary",
        2: "bg-tertiary-container text-tertiary",
    }
    for idx, customer in enumerate(top_payers_qs, start=1):
        rank_class = rank_class_map.get(idx, "bg-surface-container-high text-on-surface-variant")
        top_payers.append({
            "rank": idx,
            "rank_class": rank_class,
            "id": _display_id(customer),
            "name": customer.name,
            "initials": _customer_initials(customer.name),
            "on_time_ratio": "—",
            "avg_payment_days": "—",
            "payment_count": customer.payment_count,
            "total_paid": _format_peso(customer.total_paid),
            "tier": "—",
            "tier_class": "bg-surface-container-high text-on-surface-variant",
        })

    payer_count = (
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True, credit_lines__payments__isnull=False)
        .distinct()
        .count()
    )

    stats = [
        {
            "key": "top_payers",
            "label": "Reliable Payers",
            "value": str(payer_count),
            "value_size": "4xl",
            "subtitle": "Recorded payments",
            "icon": "verified",
            "accent": "tertiary",
            "col_span": "md:col-span-6",
        },
        {
            "key": "prompt_returners",
            "label": "Prompt Returners",
            "value": "0",
            "value_size": "4xl",
            "subtitle": "No return data yet",
            "icon": "cached",
            "accent": "tertiary",
            "col_span": "md:col-span-3",
        },
        {
            "key": "avg_pay_time",
            "label": "Avg Pay Turnaround",
            "value": "—",
            "value_size": "4xl",
            "subtitle": "Across all debtors",
            "icon": "timer",
            "accent": "primary",
            "col_span": "md:col-span-3",
        },
    ]
    return {
        "ranking_stats": stats,
        "top_payers": top_payers,
        "prompt_returners": [],
    }


def get_customer_by_display_id(user: "UserType", customer_id: str) -> Customer | None:
    """Resolves a customer from a display id such as ``HY-0001``."""
    pk = _parse_display_id(customer_id)
    if pk is None:
        return None
    return (
        Customer.objects.for_user(user)
        .filter(pk=pk, deleted_at__isnull=True)
        .first()
    )


def get_customer_table_context(
    user: "UserType",
    sort_field: str = DEFAULT_SORT,
    direction: str = DEFAULT_DIR,
) -> dict:
    """Returns the full customer table partial context."""
    sort_key = SORT_FIELD_MAP.get(sort_field, SORT_FIELD_MAP[DEFAULT_SORT])
    reverse = direction == "desc"
    next_dir = "desc" if direction == "asc" else "asc"

    rows = [
        _customer_row(c)
        for c in Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True)
        .order_by("name")
    ]
    rows.sort(key=lambda c: c.get(sort_key, 0), reverse=reverse)

    total = len(rows)
    return {
        "filters": _customer_filters(user),
        "customers": rows,
        "pagination": _pagination(1, total),
        "sort_state": {
            "field": sort_field,
            "direction": direction,
            "next_dir": next_dir,
        },
    }


def get_customer_list_context(user: "UserType") -> dict:
    """Returns the full Customers page context for all three tabs."""
    table_context = get_customer_table_context(user)
    debt_stats, debt_rows = _debt_stats_and_rows(user)
    ranking_context = _ranking_context(user)

    return {
        "today_date": datetime.now().strftime("%A, %b %d, %Y"),
        "stats": _customer_stats(user),
        "filters": table_context["filters"],
        "customers": table_context["customers"],
        "pagination": table_context["pagination"],
        "sort_state": table_context["sort_state"],
        "debt_count": len(debt_rows),
        "debt_stats": debt_stats,
        "debt_rows": debt_rows,
        "debt_pagination": _pagination(1, len(debt_rows)),
        **ranking_context,
    }


def get_customer_detail_context(customer: Customer) -> dict:
    """Returns the detail modal context for a single customer."""
    row = _customer_row(customer)
    row.update(
        {
            "member_since": customer.created_at.strftime("%b %Y"),
            "total_credits": customer.credit_lines.count(),
            "last_payment_at": _days_ago(_last_payment_dt(customer)),
            "status_badge_class": _customer_status_badge_class(customer.status),
            "status_label": _customer_status_label(customer.status),
            "can_delete": (
                _customer_borrowed_total(customer) == 0 and not row["has_debt"]
            ),
        }
    )
    return {"customer": row}


def get_customer_collect_context(customer: Customer) -> dict:
    """Returns the collect modal context grouped by rider."""
    open_lines = (
        CreditLine.objects.filter(customer=customer, qty_remaining__gt=0)
        .select_related(
            "product",
            "remittance_rider_product__remittance_rider__rider",
        )
        .order_by("product__name")
    )

    groups: dict[str, dict] = {}
    for line in open_lines:
        rr = getattr(line, "remittance_rider_product", None)
        if rr is not None:
            rider_obj = rr.remittance_rider.rider
            r_id = rider_obj.pk
            r_name = rider_obj.full_name
            r_initials = user_initials(rider_obj)
            r_driver_code = user_driver_code(rider_obj)
        else:
            r_id = "unassigned"
            r_name = "Unassigned"
            r_initials = "NA"
            r_driver_code = "N/A"

        key = f"rider-{r_id}"
        if key not in groups:
            groups[key] = {
                "rider": {
                    "id": str(r_id),
                    "name": r_name,
                    "initials": r_initials,
                    "driver_code": r_driver_code,
                },
                "items": [],
            }

        product_name = line.product.name
        if line.product.variation:
            product_name = f"{product_name} — {line.product.variation}"

        groups[key]["items"].append(
            {
                "id": f"CL-{line.pk}",
                "product": product_name,
                "qty_credited": line.qty_credited,
                "qty_remaining": line.qty_remaining,
                "unit_price": _format_peso(line.unit_price_snapshot),
                "total_credit": _format_peso(line.total_credit_amount),
                "rider": groups[key]["rider"],
            }
        )

    rider_groups = sorted(groups.values(), key=lambda g: g["rider"]["name"])
    all_credit_lines = [item for group in rider_groups for item in group["items"]]
    return {
        "customer": _customer_row(customer),
        "rider_groups": rider_groups,
        "credit_lines": all_credit_lines,
        "borrowed_entries": [],
    }


def get_record_debt_context(user: "UserType") -> dict:
    """Context for the record-debt modal: customer and product dropdowns."""
    customers = (
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True)
        .order_by("name")
    )
    products = (
        Product.objects.for_user(user)
        .filter(deleted_at__isnull=True, deactivated_at__isnull=True)
        .order_by("name", "variation")
    )
    return {
        "customers": [
            {"id": _display_id(c), "name": c.name} for c in customers
        ],
        "products": [
            {
                "key": str(p.pk),
                "label": f"{p.name} — {p.variation}" if p.variation else p.name,
                "unit_price": f"{p.price:.2f}",
            }
            for p in products
        ],
    }


def get_record_borrowed_context(user: "UserType") -> dict:
    """Context for the record-borrowed modal."""
    customers = (
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True)
        .order_by("name")
    )
    return {
        "customers": [
            {"id": _display_id(c), "name": c.name} for c in customers
        ],
        "container_types": [
            {"key": "round_8gal", "label": "Round 8gal"},
            {"key": "slim_8gal", "label": "Slim 8gal"},
            {"key": "other", "label": "Other"},
        ],
    }
