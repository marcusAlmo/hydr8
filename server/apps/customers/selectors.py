"""Read-side selectors for the Customers pages.

Selectors return dicts shaped for ``customer_list.html`` and its
partials.  Views call these — they never hit the ORM directly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.paginator import Paginator
from django.db.models import Count, F, Min, Q, Sum
from django.utils import timezone

from apps.core.models import Product
from apps.settings.selectors import get_overdue_threshold_days
from apps.users.models import User
from apps.users.presentation import driver_code as user_driver_code
from apps.users.presentation import initials as user_initials

from .models import BorrowedContainer, Customer, CreditLine, CreditPayment

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
PER_PAGE = 25

# Maps sort field names to actual DB column/annotation names for DB-side sorting.
# "last_credit" maps to "last_credit_at" with inverted direction (more recent = fewer days).
_DB_SORT_MAP: dict[str, str] = {
    "name": "name",
    "debt_balance": "debt_balance",
    "borrowed_total": "borrowed_total",  # annotated
    "payable_amount": "debt_balance",     # same value as debt_balance
    "last_credit": "last_credit_at",      # direction inverted below
}

# ---------------------------------------------------------------------------
# Sort mapping for the debt-management table HTMX partial.
# ---------------------------------------------------------------------------
DEBT_SORT_FIELD_MAP: dict[str, str] = {
    "name": "name",
    "debt_balance": "debt_balance",
    "age": "oldest_credit_at",            # annotated (min active CreditLine.created_at)
    "days_overdue": "last_credit_at",      # direction inverted below
    "borrowed_total": "borrowed_total",    # annotated
}
DEBT_DEFAULT_SORT = "debt_balance"
DEBT_DEFAULT_DIR = "desc"
DEBT_PER_PAGE = 25

# Maps debt sort field names to actual DB column/annotation names for DB-side sorting.
_DEBT_DB_SORT_MAP: dict[str, str] = {
    "name": "name",
    "debt_balance": "debt_balance",
    "age": "oldest_credit_at",             # annotated
    "days_overdue": "last_credit_at",       # direction inverted below
    "borrowed_total": "borrowed_total",     # annotated
}


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
        "credit_limit_value": customer.credit_limit,
    }


def _debt_row(customer: Customer, overdue_threshold: int = 7) -> dict:
    """Converts a ``Customer`` into the debt-management row shape.

    ``overdue_threshold`` is the configured number of days after which
    a debt is considered overdue (from SystemConfig). It drives the
    ``days_overdue_class`` severity coloring.

    ``customer.oldest_credit_at`` is expected to be annotated on the
    queryset by ``get_debt_table_context`` — it is the min ``created_at``
    among the customer's active credit lines (``qty_remaining > 0``).
    The ``age`` field is the number of days since that date.
    """
    days_overdue = _days_since(customer.last_credit_at)
    oldest_credit_at = getattr(customer, "oldest_credit_at", None)
    age = _days_since(oldest_credit_at) if oldest_credit_at else 0

    if days_overdue > overdue_threshold:
        days_class = "text-error"
    else:
        days_class = "text-on-surface-variant"

    return {
        "id": _display_id(customer),
        "name": customer.name,
        "initials": _customer_initials(customer.name),
        "debt_balance": _format_peso(customer.debt_balance),
        "age": age,
        "days_overdue": days_overdue,
        "days_overdue_class": days_class,
        "is_overdue": days_overdue > overdue_threshold,
        "borrowed_total": _customer_borrowed_total(customer),
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


def _pagination_from_page(page_obj) -> dict:
    """Builds the pagination context dict from a Django Page object."""
    total = page_obj.paginator.count
    if total == 0:
        return {
            "showing_from": 0,
            "showing_to": 0,
            "total": 0,
            "total_display": "0",
            "current_page": page_obj.number,
            "total_pages": page_obj.paginator.num_pages,
            "has_previous": False,
            "has_next": False,
            "previous_page_number": None,
            "next_page_number": None,
        }
    return {
        "showing_from": page_obj.start_index(),
        "showing_to": page_obj.end_index(),
        "total": total,
        "total_display": f"{total:,}",
        "current_page": page_obj.number,
        "total_pages": page_obj.paginator.num_pages,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
        "previous_page_number": page_obj.previous_page_number() if page_obj.has_previous() else None,
        "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None,
    }


def _pagination(current_page: int, total: int) -> dict:
    """Legacy fake pagination — used only by debt/ranking tabs (small datasets)."""
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


def _debt_stats(user: "UserType") -> list[dict]:
    """Summary stat cards for the debt-management tab."""
    threshold = get_overdue_threshold_days(user)
    debtors = (
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True, debt_balance__gt=0)
    )
    debtor_count = debtors.count()
    total_debt = (
        debtors.aggregate(Sum("debt_balance"))["debt_balance__sum"]
        or Decimal("0.00")
    )

    # Stats are computed across the full debtor set (not the paginated page).
    debtors_list = list(debtors.only("last_credit_at", "debt_balance"))
    overdue_count = sum(1 for c in debtors_list if _days_since(c.last_credit_at) > threshold)
    overdue_amount = sum(
        c.debt_balance for c in debtors_list if _days_since(c.last_credit_at) > threshold
    )
    avg_days = (
        round(sum(_days_since(c.last_credit_at) for c in debtors_list) / debtor_count)
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
            "key": "overdue",
            "label": f"Overdue {threshold}+ Days",
            "value": str(overdue_count),
            "value_size": "4xl",
            "subtitle": _format_peso(overdue_amount) + " at risk",
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
    return stats


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
    query: str = "",
    page: int = 1,
) -> dict:
    """Returns the full customer table partial context.

    When ``query`` is non-empty, filters by ``name__icontains``.
    Uses DB-side sorting and real pagination (PER_PAGE=25).
    """
    next_dir = "desc" if direction == "asc" else "asc"

    qs = Customer.objects.for_user(user).filter(deleted_at__isnull=True)

    # Apply search filter
    query = (query or "").strip()
    if query:
        qs = qs.filter(name__icontains=query)

    # Annotate borrowed_total for sorting
    qs = qs.annotate(
        borrowed_total=F("borrowed_round_8gal") + F("borrowed_slim_8gal") + F("borrowed_other")
    )

    # DB-side sorting
    db_sort = _DB_SORT_MAP.get(sort_field, _DB_SORT_MAP[DEFAULT_SORT])
    if sort_field == "last_credit":
        # Invert direction: last_credit_days asc = last_credit_at desc
        if direction == "asc":
            qs = qs.order_by(F("last_credit_at").desc(nulls_last=True))
        else:
            qs = qs.order_by(F("last_credit_at").asc(nulls_last=True))
    else:
        if direction == "desc":
            db_sort = f"-{db_sort}"
        qs = qs.order_by(db_sort)

    # Real pagination
    paginator = Paginator(qs, PER_PAGE)
    page_obj = paginator.get_page(page)

    rows = [_customer_row(c) for c in page_obj.object_list]

    return {
        "filters": _customer_filters(user),
        "customers": rows,
        "pagination": _pagination_from_page(page_obj),
        "sort_state": {
            "field": sort_field,
            "direction": direction,
            "next_dir": next_dir,
        },
        "search_query": query,
    }


def get_debt_table_context(
    user: "UserType",
    sort_field: str = DEBT_DEFAULT_SORT,
    direction: str = DEBT_DEFAULT_DIR,
    query: str = "",
    page: int = 1,
) -> dict:
    """Returns the debt-management table partial context.

    Filters to customers with ``debt_balance > 0``. When ``query`` is
    non-empty, filters by ``name__icontains``. Uses DB-side sorting and
    real pagination (``DEBT_PER_PAGE``).
    """
    next_dir = "desc" if direction == "asc" else "asc"

    qs = (
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True, debt_balance__gt=0)
    )

    # Apply search filter
    query = (query or "").strip()
    if query:
        qs = qs.filter(name__icontains=query)

    # Annotate borrowed_total and oldest_credit_at for sorting/display.
    # oldest_credit_at = min created_at among active credit lines
    # (qty_remaining > 0), used to compute the "age" of the debt.
    qs = qs.annotate(
        borrowed_total=F("borrowed_round_8gal") + F("borrowed_slim_8gal") + F("borrowed_other"),
        oldest_credit_at=Min(
            "credit_lines__created_at",
            filter=Q(credit_lines__qty_remaining__gt=0),
        ),
    )

    # DB-side sorting
    db_sort = _DEBT_DB_SORT_MAP.get(sort_field, _DEBT_DB_SORT_MAP[DEBT_DEFAULT_SORT])
    if sort_field == "days_overdue":
        # Invert direction: days_overdue asc = last_credit_at desc (recent = fewer days)
        if direction == "asc":
            qs = qs.order_by(F("last_credit_at").desc(nulls_last=True))
        else:
            qs = qs.order_by(F("last_credit_at").asc(nulls_last=True))
    else:
        if direction == "desc":
            db_sort = f"-{db_sort}"
        qs = qs.order_by(db_sort)

    # Real pagination
    paginator = Paginator(qs, DEBT_PER_PAGE)
    page_obj = paginator.get_page(page)

    threshold = get_overdue_threshold_days(user)
    rows = [_debt_row(c, overdue_threshold=threshold) for c in page_obj.object_list]

    return {
        "debt_rows": rows,
        "debt_pagination": _pagination_from_page(page_obj),
        "debt_sort_state": {
            "field": sort_field,
            "direction": direction,
            "next_dir": next_dir,
        },
        "debt_search_query": query,
    }


def get_customer_list_context(user: "UserType") -> dict:
    """Returns the full Customers page context for all three tabs."""
    table_context = get_customer_table_context(user)
    debt_stats = _debt_stats(user)
    debt_table_context = get_debt_table_context(user)
    ranking_context = _ranking_context(user)

    return {
        "today_date": datetime.now().strftime("%A, %b %d, %Y"),
        "stats": _customer_stats(user),
        "filters": table_context["filters"],
        "customers": table_context["customers"],
        "pagination": table_context["pagination"],
        "sort_state": table_context["sort_state"],
        "search_query": table_context["search_query"],
        "debt_count": debt_table_context["debt_pagination"]["total"],
        "debt_stats": debt_stats,
        "debt_rows": debt_table_context["debt_rows"],
        "debt_pagination": debt_table_context["debt_pagination"],
        "debt_sort_state": debt_table_context["debt_sort_state"],
        "debt_search_query": debt_table_context["debt_search_query"],
        **ranking_context,
    }


def get_customer_detail_context(customer: Customer, user: "UserType | None" = None) -> dict:
    """Returns the detail modal context for a single customer.

    When ``user`` is provided, the configurable overdue threshold is read
    from SystemConfig and used to compute ``is_overdue`` — whether the
    customer's last credit is older than the threshold. This drives the
    "Action required — overdue balance" indicator in the modal.
    """
    row = _customer_row(customer)
    threshold = get_overdue_threshold_days(user) if user is not None else 7
    days_since_credit = _days_since(customer.last_credit_at)
    is_overdue = row["has_debt"] and days_since_credit > threshold
    row.update(
        {
            "member_since": customer.created_at.strftime("%b %Y"),
            "total_credits": customer.credit_lines.count(),
            "last_payment_at": _days_ago(_last_payment_dt(customer)),
            "status_badge_class": _customer_status_badge_class(customer.status),
            "status_label": _customer_status_label(customer.status),
            "is_overdue": is_overdue,
            "overdue_threshold_days": threshold,
            "can_delete": (
                _customer_borrowed_total(customer) == 0 and not row["has_debt"]
            ),
        }
    )
    return {"customer": row}


def get_customer_collect_context(customer: Customer) -> dict:
    """Returns the collect modal context grouped by rider.

    Credit lines are grouped by the rider who delivered them (via
    ``remittance_rider_product``); borrowed containers are grouped by
    their ``care_of`` user so responsibility is visible per item. Both
    carry a ``care_of`` field rendered in the list of borrowed/credited.
    """
    open_lines = (
        CreditLine.objects.filter(customer=customer, qty_remaining__gt=0)
        .select_related(
            "product",
            "care_of",
            "care_of__role",
            "remittance_rider_product__remittance_rider__rider",
        )
        .order_by("product__name")
    )

    open_borrowed = (
        BorrowedContainer.objects.filter(customer=customer, qty_returned__lt=F("qty_borrowed"))
        .select_related("care_of", "care_of__role")
        .order_by("-created_at")
    )

    groups: dict[str, dict] = {}

    def _ensure_group(key: str, rider: dict) -> dict:
        if key not in groups:
            groups[key] = {"rider": rider, "items": []}
        return groups[key]

    def _care_of_summary(user) -> dict:
        if user is None:
            return {"name": "Unassigned", "initials": "NA"}
        return {
            "name": user.full_name,
            "initials": user_initials(user),
        }

    for line in open_lines:
        rr = getattr(line, "remittance_rider_product", None)
        if rr is not None:
            rider_obj = rr.remittance_rider.rider
            r_id = rider_obj.pk
            r_name = rider_obj.full_name
            r_initials = user_initials(rider_obj)
            r_driver_code = user_driver_code(rider_obj)
        elif line.care_of is not None:
            # Manual debt records have no remittance rider product; fall
            # back to the ``care_of`` user (the staff/rider who extended
            # the credit) so the collect modal groups them under the
            # responsible person instead of "Unassigned".
            rider_obj = line.care_of
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
        group = _ensure_group(
            key,
            {
                "id": str(r_id),
                "name": r_name,
                "initials": r_initials,
                "driver_code": r_driver_code,
            },
        )

        product_name = line.product.name
        if line.product.variation:
            product_name = f"{product_name} — {line.product.variation}"

        group["items"].append(
            {
                "id": f"CL-{line.pk}",
                "product": product_name,
                "qty_credited": line.qty_credited,
                "qty_remaining": line.qty_remaining,
                "unit_price": _format_peso(line.unit_price_snapshot),
                "total_credit": _format_peso(line.total_credit_amount),
                "rider": group["rider"],
                "care_of": _care_of_summary(line.care_of),
            }
        )

    for borrowed in open_borrowed:
        care_of_user = borrowed.care_of
        if care_of_user is not None:
            r_id = care_of_user.pk
            r_name = care_of_user.full_name
            r_initials = user_initials(care_of_user)
            r_driver_code = user_driver_code(care_of_user)
        else:
            r_id = "unassigned"
            r_name = "Unassigned"
            r_initials = "NA"
            r_driver_code = "N/A"

        key = f"rider-{r_id}"
        group = _ensure_group(
            key,
            {
                "id": str(r_id),
                "name": r_name,
                "initials": r_initials,
                "driver_code": r_driver_code,
            },
        )

        group["items"].append(
            {
                "id": f"BC-{borrowed.pk}",
                "container_key": borrowed.container_key,
                "container_label": borrowed.container_label,
                "qty_borrowed": borrowed.qty_borrowed,
                "outstanding": borrowed.qty_remaining,
                "rider": group["rider"],
                "care_of": _care_of_summary(borrowed.care_of),
            }
        )

    rider_groups = sorted(groups.values(), key=lambda g: g["rider"]["name"])
    all_credit_lines = [item for group in rider_groups for item in group["items"]]
    borrowed_entries = [item for group in rider_groups for item in group["items"] if item.get("container_key")]
    return {
        "customer": _customer_row(customer),
        "rider_groups": rider_groups,
        "credit_lines": all_credit_lines,
        "borrowed_entries": borrowed_entries,
    }


def _care_of_users(user: "UserType") -> list[dict]:
    """Active users in the operator's tenant, for the ``care of`` dropdown.

    Includes admins, staff, and drivers — anyone who could be responsible
    for lending containers or extending credit to a customer.
    """
    qs = User.objects.filter(deleted_at__isnull=True, is_active=True)
    if not user.is_superuser and user.company_id is not None:
        qs = qs.filter(company_id=user.company_id)
    qs = qs.order_by("first_name", "last_name", "username")
    users: list[dict] = []
    for u in qs:
        label = u.full_name
        if u.role_id is not None and getattr(u.role, "name", None):
            label = f"{label} ({u.role.name})"
        users.append({"id": str(u.pk), "label": label})
    return users


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
        "care_of_users": _care_of_users(user),
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
        "care_of_users": _care_of_users(user),
    }


def get_customer_edit_context(customer: Customer) -> dict:
    """Returns the edit modal context for a single customer."""
    return {"customer": _customer_row(customer)}
