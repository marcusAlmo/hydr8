"""Presentation helpers for the Customers pages.

This module takes *raw data* returned by :mod:`apps.customers.selectors`
and shapes it into template-ready dicts — currency strings, CSS class
maps, label strings, card/row dicts.  It contains no ORM queries and no
business rules beyond display-flag derivation.

The public ``get_*_context`` functions are the composition entry points
called by views; they fetch raw data from selectors and shape the final
context dicts that templates consume.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from django.utils import timezone

from apps.users.presentation import driver_code as user_driver_code
from apps.users.presentation import initials as user_initials

from .models import BorrowedContainer, Customer, CreditLine, CreditPayment
from .selectors import (
    DEFAULT_DIR,
    DEFAULT_SORT,
    _history_entry_deletable,
    _history_entry_editable,
    _last_payment_dt,
    care_of_users_qs,
    customer_collect_raw,
    customer_detail_raw,
    customer_filter_counts,
    customer_history_raw,
    customer_stats_raw,
    customer_table_page,
    payer_count,
    record_borrowed_raw,
    record_debt_raw,
    top_payers,
)

if TYPE_CHECKING:
    from apps.users.models import User as UserType


_CUSTOMER_DISPLAY_PREFIX = "HY"


# ---------------------------------------------------------------------------
# Pure formatting helpers
# ---------------------------------------------------------------------------

def display_id(customer: Customer) -> str:
    """Human-readable customer code, e.g. ``HY-0001``."""
    return f"{_CUSTOMER_DISPLAY_PREFIX}-{customer.pk:04d}"


def customer_initials(name: str) -> str:
    """Returns a 2-character initial string from a customer name."""
    name = (name or "").strip()
    if not name:
        return "?"
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()
    return parts[0][:2].upper()


def format_peso(value) -> str:
    """Format a Decimal/float as a Philippine peso string."""
    try:
        return f"₱{float(value):,.2f}"
    except (TypeError, ValueError):
        return "₱0.00"


def days_since(dt) -> int:
    """Days elapsed since ``dt``; 9999 means no date was provided."""
    if not dt:
        return 9999
    now = timezone.now()
    if dt > now:
        return 0
    return (now - dt).days


def days_ago_text(dt) -> str:
    """Human-friendly relative time string."""
    days = days_since(dt)
    if days == 9999:
        return "Never"
    if days == 0:
        return "Today"
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


def customer_borrowed_total(customer: Customer) -> int:
    """Total unreturned containers for a customer."""
    return (
        customer.borrowed_round_8gal
        + customer.borrowed_slim_8gal
        + customer.borrowed_other
    )


def customer_row_border(status: str) -> str:
    return {
        Customer.Status.ACTIVE: "border-l-transparent",
        Customer.Status.FLAGGED: "border-l-[#D97706]",
        Customer.Status.BLACKLISTED: "border-l-error",
    }.get(status, "border-l-transparent")


def customer_anomaly_badge(status: str) -> str:
    if status == Customer.Status.ACTIVE:
        return ""
    return status.upper()


def customer_status_badge_class(status: str) -> str:
    return {
        Customer.Status.ACTIVE: "bg-tertiary-container/30 text-tertiary border-tertiary/30",
        Customer.Status.FLAGGED: "bg-[#D97706]/15 text-[#D97706] border-[#D97706]/30",
        Customer.Status.BLACKLISTED: "bg-error/10 text-error border-error/30",
    }.get(status, "bg-tertiary-container/30 text-tertiary border-tertiary/30")


def customer_status_label(status: str) -> str:
    return {
        Customer.Status.ACTIVE: "Active",
        Customer.Status.FLAGGED: "Flagged",
        Customer.Status.BLACKLISTED: "Blacklisted",
    }.get(status, status.title())


def customer_row(customer: Customer) -> dict:
    """Converts a ``Customer`` into the table/detail row shape."""
    debt = customer.debt_balance
    borrowed_total = customer_borrowed_total(customer)
    has_debt = debt > 0
    status = customer.status
    return {
        "id": display_id(customer),
        "pk": customer.pk,
        "name": customer.name,
        "initials": customer_initials(customer.name),
        "debt_balance": format_peso(debt),
        "debt_balance_raw": float(debt),
        "debt_class": "text-error" if has_debt else "text-tertiary",
        "borrowed_round_8gal": customer.borrowed_round_8gal,
        "borrowed_slim_8gal": customer.borrowed_slim_8gal,
        "borrowed_other": customer.borrowed_other,
        "borrowed_total": borrowed_total,
        "borrowed_class": "text-on-surface-variant",
        "payable_amount": format_peso(debt),
        "payable_amount_raw": float(debt),
        "last_credit_at": days_ago_text(customer.last_credit_at),
        "last_credit_days": days_since(customer.last_credit_at),
        "row_border": customer_row_border(status),
        "has_debt": has_debt,
        "status": status,
        "anomaly_badge": customer_anomaly_badge(status),
        "anomaly_reason": customer.flagged_reason or "",
        "credit_limit": (
            format_peso(customer.credit_limit)
            if customer.credit_limit and customer.credit_limit > 0
            else "Not set"
        ),
        "credit_limit_value": customer.credit_limit,
    }


def pagination_from_page(page_obj) -> dict:
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


def pagination(current_page: int, total: int) -> dict:
    """Legacy fake pagination — used only by debt/ranking tabs (small datasets)."""
    return {
        "showing_from": 1 if total else 0,
        "showing_to": total,
        "total": total,
        "total_display": f"{total:,}",
        "current_page": current_page,
        "total_pages": 1 if total else 1,
    }


def care_of_summary(user) -> dict:
    """Returns a ``{name, initials}`` summary for a ``care_of`` user."""
    if user is None:
        return {"name": "Unassigned", "initials": "NA"}
    return {
        "name": user.full_name,
        "initials": user_initials(user),
    }


def care_of_users(users) -> list[dict]:
    """Shapes the ``care of`` dropdown dicts from raw ``User`` instances."""
    result: list[dict] = []
    for u in users:
        label = u.full_name
        if u.role_id is not None and getattr(u.role, "name", None):
            label = f"{label} ({u.role.name})"
        result.append({"id": str(u.pk), "label": label})
    return result


# ---------------------------------------------------------------------------
# Dict-shaping functions (compose selectors + formatting)
# ---------------------------------------------------------------------------

def customer_filters(counts: dict[str, int]) -> list[dict]:
    """Shapes the filter-bucket dicts from raw counts."""
    return [
        {
            "label": "All",
            "count": counts["all"],
            "active": True,
        },
        {
            "label": "Has Debt",
            "count": counts["has_debt"],
            "active": False,
        },
        {
            "label": "Has Borrowed Items",
            "count": counts["has_borrowed"],
            "active": False,
        },
        {
            "label": "Anomalous",
            "count": counts["anomalous"],
            "active": False,
        },
    ]


def customer_stats(user: "UserType") -> list[dict]:
    """Summary stat cards for the Summary tab."""
    raw = customer_stats_raw(user)
    total = raw["total"]
    debtor_count = raw["debtor_count"]
    total_debt = raw["total_debt"]
    borrowed_total = raw["borrowed_total"]
    borrowed_count = raw["borrowed_count"]
    overdue_count = raw["overdue_count"]
    avg_days = raw["avg_days"]
    threshold = raw["threshold"]

    return [
        {
            "key": "total_customers",
            "label": "Total Customers",
            "value": f"{total:,}",
            "raw_value": total,
            "value_prefix": "",
            "value_decimals": 0,
            "value_size": "4xl",
            "subtitle": "Active accounts",
            "icon": "group",
            "accent": "primary",
            "col_span": "md:col-span-4",
        },
        {
            "key": "total_debt",
            "label": "Total Outstanding",
            "value": format_peso(total_debt),
            "raw_value": float(total_debt),
            "value_prefix": "₱",
            "value_decimals": 2,
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
            "raw_value": borrowed_total,
            "value_prefix": "",
            "value_decimals": 0,
            "value_size": "4xl",
            "subtitle": f"Across {borrowed_count} customers",
            "icon": "water_damage",
            "accent": "warning",
            "col_span": "md:col-span-4",
        },
        {
            "key": "overdue",
            "label": f"Overdue {threshold}+ Days",
            "value": str(overdue_count),
            "raw_value": overdue_count,
            "value_prefix": "",
            "value_decimals": 0,
            "value_size": "4xl",
            "subtitle": "Debtors past the threshold",
            "icon": "schedule",
            "accent": "warning",
            "col_span": "md:col-span-6",
        },
        {
            "key": "avg_days_overdue",
            "label": "Avg Days Overdue",
            "value": str(avg_days),
            "raw_value": avg_days,
            "value_prefix": "",
            "value_decimals": 0,
            "value_size": "4xl",
            "subtitle": "Across active debtors",
            "icon": "hourglass_top",
            "accent": "warning",
            "col_span": "md:col-span-6",
        },
    ]


def ranking_context(user: "UserType") -> dict:
    top_payers_list = top_payers(user)
    rank_class_map = {
        1: "bg-tertiary text-on-primary",
        2: "bg-tertiary-container text-tertiary",
    }
    top_payer_rows: list[dict] = []
    for idx, customer in enumerate(top_payers_list, start=1):
        rank_class = rank_class_map.get(idx, "bg-surface-container-high text-on-surface-variant")
        top_payer_rows.append({
            "rank": idx,
            "rank_class": rank_class,
            "id": display_id(customer),
            "name": customer.name,
            "initials": customer_initials(customer.name),
            "on_time_ratio": "—",
            "avg_payment_days": "—",
            "payment_count": customer.payment_count,
            "total_paid": format_peso(customer.total_paid),
            "tier": "—",
            "tier_class": "bg-surface-container-high text-on-surface-variant",
        })

    count = payer_count(user)

    stats = [
        {
            "key": "top_payers",
            "label": "Reliable Payers",
            "value": str(count),
            "raw_value": count,
            "value_prefix": "",
            "value_decimals": 0,
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
            "raw_value": 0,
            "value_prefix": "",
            "value_decimals": 0,
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
            "raw_value": None,
            "value_prefix": "",
            "value_decimals": 0,
            "value_size": "4xl",
            "subtitle": "Across all debtors",
            "icon": "timer",
            "accent": "primary",
            "col_span": "md:col-span-3",
        },
    ]
    return {
        "ranking_stats": stats,
        "top_payers": top_payer_rows,
        "prompt_returners": [],
    }


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
    raw = customer_table_page(user, sort_field, direction, query, page)
    rows = [customer_row(c) for c in raw["page_obj"].object_list]

    return {
        "filters": customer_filters(customer_filter_counts(user)),
        "customers": rows,
        "pagination": pagination_from_page(raw["page_obj"]),
        "sort_state": {
            "field": raw["sort_field"],
            "direction": raw["direction"],
            "next_dir": raw["next_dir"],
        },
        "search_query": raw["query"],
    }


def get_customer_list_context(user: "UserType") -> dict:
    """Returns the full Customers page context for the Summary and Ranking tabs.

    The Debt Management tab has been retired — its KPIs (total outstanding,
    overdue 7+ days, avg days overdue) have been migrated into the Summary
    tab's stats row, and the Record Borrowed / Record Debt actions now live
    in the Summary tab's action bar.
    """
    table_context = get_customer_table_context(user)
    ranking = ranking_context(user)

    return {
        "today_date": timezone.localtime().strftime("%A, %b %d, %Y"),
        "stats": customer_stats(user),
        "filters": table_context["filters"],
        "customers": table_context["customers"],
        "pagination": table_context["pagination"],
        "sort_state": table_context["sort_state"],
        "search_query": table_context["search_query"],
        **ranking,
    }


def get_customer_detail_context(customer: Customer, user: "UserType | None" = None) -> dict:
    """Returns the detail modal context for a single customer.

    When ``user`` is provided, the configurable overdue threshold is read
    from SystemConfig and used to compute ``is_overdue`` — whether the
    customer's last credit is older than the threshold. This drives the
    "Action required — overdue balance" indicator in the modal.
    """
    row = customer_row(customer)
    raw = customer_detail_raw(customer, user)
    days_since_credit = days_since(customer.last_credit_at)
    is_overdue = row["has_debt"] and days_since_credit > raw["threshold"]
    row.update(
        {
            "address": customer.address or "",
            "contact_number": customer.contact_number or "",
            "member_since": customer.created_at.strftime("%b %Y"),
            "total_credits": raw["total_credits"],
            "last_payment_at": days_ago_text(raw["last_payment_dt"]),
            "status_badge_class": customer_status_badge_class(customer.status),
            "status_label": customer_status_label(customer.status),
            "is_overdue": is_overdue,
            "overdue_threshold_days": raw["threshold"],
            "can_delete": (
                customer_borrowed_total(customer) == 0 and not row["has_debt"]
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
    open_lines, open_borrowed = customer_collect_raw(customer)

    groups: dict[str, dict] = {}

    def _ensure_group(key: str, rider: dict) -> dict:
        if key not in groups:
            groups[key] = {"rider": rider, "items": []}
        return groups[key]

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

        remaining_balance = Decimal(line.qty_remaining) * line.unit_price_snapshot
        group["items"].append(
            {
                "id": f"CL-{line.pk}",
                "product": product_name,
                "qty_credited": line.qty_credited,
                "qty_remaining": line.qty_remaining,
                "unit_price": format_peso(line.unit_price_snapshot),
                "unit_price_num": str(line.unit_price_snapshot),
                "total_credit": format_peso(line.total_credit_amount),
                "remaining_balance": format_peso(remaining_balance),
                "rider": group["rider"],
                "care_of": care_of_summary(line.care_of),
                "transaction_date": line.transaction_date.strftime("%b %d, %Y") if line.transaction_date else "",
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
                "care_of": care_of_summary(borrowed.care_of),
                "transaction_date": borrowed.transaction_date.strftime("%b %d, %Y") if borrowed.transaction_date else "",
            }
        )

    rider_groups = sorted(groups.values(), key=lambda g: g["rider"]["name"])
    all_credit_lines = [item for group in rider_groups for item in group["items"]]
    borrowed_entries = [item for group in rider_groups for item in group["items"] if item.get("container_key")]
    return {
        "customer": customer_row(customer),
        "rider_groups": rider_groups,
        "credit_lines": all_credit_lines,
        "borrowed_entries": borrowed_entries,
    }


def get_record_debt_context(user: "UserType") -> dict:
    """Context for the record-debt modal: customer and product dropdowns."""
    customers, products, users = record_debt_raw(user)
    customer_list = [
        {"id": display_id(c), "name": c.name} for c in customers
    ]
    return {
        "customers": customer_list,
        "customers_json": customer_list,
        "products": [
            {
                "key": str(p.pk),
                "label": f"{p.name} — {p.variation}" if p.variation else p.name,
                "unit_price": f"{p.price:.2f}",
            }
            for p in products
        ],
        "care_of_users": care_of_users(users),
    }


def get_record_borrowed_context(user: "UserType") -> dict:
    """Context for the record-borrowed modal."""
    customers, users = record_borrowed_raw(user)
    customer_list = [
        {"id": display_id(c), "name": c.name} for c in customers
    ]
    return {
        "customers": customer_list,
        "customers_json": customer_list,
        "container_types": [
            {"key": "round_8gal", "label": "Round 8gal"},
            {"key": "slim_8gal", "label": "Slim 8gal"},
            {"key": "other", "label": "Other"},
        ],
        "care_of_users": care_of_users(users),
    }


# ---------------------------------------------------------------------------
# History ledger presentation
# ---------------------------------------------------------------------------

def format_history_timestamp(dt) -> str:
    if not dt:
        return "—"
    return timezone.localtime(dt).strftime("%b %d, %Y %I:%M %p")


def history_sort_key(dt: datetime | None) -> datetime:
    """Returns a stable sort key for a history entry."""
    return dt or timezone.now()


def history_credit_line(line: CreditLine, user: "UserType") -> dict:
    product_name = line.product.name
    if line.product.variation:
        product_name = f"{product_name} — {line.product.variation}"
    is_editable, reason = _history_entry_editable(line, user)
    is_deletable, del_reason = _history_entry_deletable(line, user)
    return {
        "kind": "credit_line",
        "pk": line.pk,
        "display_id": f"CL-{line.pk}",
        "sort_key": history_sort_key(line.created_at),
        "timestamp": format_history_timestamp(line.created_at),
        "transaction_date": line.transaction_date.strftime("%b %d, %Y"),
        "title": f"Debt recorded: {product_name}",
        "product": product_name,
        "qty_credited": line.qty_credited,
        "unit_price": format_peso(line.unit_price_snapshot),
        "unit_price_num": str(line.unit_price_snapshot),
        "total_credit": format_peso(line.total_credit_amount),
        "qty_remaining": line.qty_remaining,
        "care_of": care_of_summary(line.care_of),
        "recorded_by": care_of_summary(line.care_of),
        "is_editable": is_editable,
        "edit_disabled_reason": reason,
        "is_deletable": is_deletable,
        "delete_disabled_reason": del_reason,
    }


def history_credit_payment(payment: CreditPayment, user: "UserType") -> dict:
    is_editable, reason = _history_entry_editable(payment, user)
    is_deletable, del_reason = _history_entry_deletable(payment, user)
    product = payment.credit_line.product.name
    if payment.credit_line.product.variation:
        product = f"{product} — {payment.credit_line.product.variation}"
    paid_at = payment.paid_at or timezone.localtime(payment.created_at).date()
    paid_at_dt = (
        datetime.combine(payment.paid_at, datetime.min.time(), tzinfo=timezone.get_current_timezone())
        if payment.paid_at
        else payment.created_at
    )
    return {
        "kind": "credit_payment",
        "pk": payment.pk,
        "display_id": f"CP-{payment.pk}",
        "sort_key": history_sort_key(paid_at_dt),
        "timestamp": format_history_timestamp(payment.created_at),
        "transaction_date": paid_at.strftime("%b %d, %Y"),
        "title": f"Payment received: {product}",
        "product": product,
        "qty_paid": payment.containers_paid,
        "amount": format_peso(payment.amount),
        "amount_num": str(payment.amount),
        "credit_line_id": f"CL-{payment.credit_line_id}",
        "care_of": care_of_summary(payment.credit_line.care_of),
        "recorded_by": care_of_summary(payment.recorded_by),
        "is_editable": is_editable,
        "edit_disabled_reason": reason,
        "is_deletable": is_deletable,
        "delete_disabled_reason": del_reason,
    }


def history_borrowed(borrowed: BorrowedContainer, user: "UserType") -> dict:
    is_editable, reason = _history_entry_editable(borrowed, user)
    is_deletable, del_reason = _history_entry_deletable(borrowed, user)
    return {
        "kind": "borrowed",
        "pk": borrowed.pk,
        "display_id": f"BC-{borrowed.pk}",
        "sort_key": history_sort_key(borrowed.created_at),
        "timestamp": format_history_timestamp(borrowed.created_at),
        "transaction_date": borrowed.transaction_date.strftime("%b %d, %Y"),
        "title": f"Borrowed: {borrowed.container_label}",
        "container_label": borrowed.container_label,
        "container_key": borrowed.container_key,
        "qty_borrowed": borrowed.qty_borrowed,
        "qty_returned": borrowed.qty_returned,
        "outstanding": borrowed.qty_remaining,
        "care_of": care_of_summary(borrowed.care_of),
        "recorded_by": care_of_summary(borrowed.recorded_by),
        "is_editable": is_editable,
        "edit_disabled_reason": reason,
        "is_deletable": is_deletable,
        "delete_disabled_reason": del_reason,
    }


def history_container_return(borrowed: BorrowedContainer, user: "UserType") -> dict | None:
    """Returns a synthetic return entry for a borrowed container with returns."""
    if borrowed.qty_returned <= 0 or not borrowed.returned_at:
        return None
    tz = timezone.get_current_timezone()
    sort_key = datetime.combine(borrowed.returned_at, datetime.min.time(), tzinfo=tz)
    return {
        "kind": "container_return",
        "pk": borrowed.pk,
        "display_id": f"BC-{borrowed.pk}",
        "sort_key": history_sort_key(sort_key),
        "timestamp": format_history_timestamp(sort_key),
        "transaction_date": borrowed.returned_at.strftime("%b %d, %Y"),
        "title": f"Returned: {borrowed.container_label}",
        "container_label": borrowed.container_label,
        "container_key": borrowed.container_key,
        "qty_returned": borrowed.qty_returned,
        "outstanding": borrowed.qty_remaining,
        "care_of": care_of_summary(borrowed.care_of),
        "recorded_by": care_of_summary(borrowed.recorded_by),
        "is_editable": False,
        "edit_disabled_reason": "Return is part of the borrowing record",
        "is_deletable": False,
        "delete_disabled_reason": "Return is part of the borrowing record",
    }


def get_customer_history_context(customer: Customer, user: "UserType") -> dict:
    """Returns a unified, chronological ledger history for the customer."""
    credit_lines, payments, borrowed = customer_history_raw(customer)

    entries: list[dict] = []
    entries.extend(history_credit_line(line, user) for line in credit_lines)
    entries.extend(history_credit_payment(payment, user) for payment in payments)
    entries.extend(history_borrowed(b, user) for b in borrowed)
    for b in borrowed:
        return_entry = history_container_return(b, user)
        if return_entry is not None:
            entries.append(return_entry)

    entries.sort(key=lambda e: e["sort_key"], reverse=True)

    return {
        "customer": customer_row(customer),
        "history": entries,
    }


def get_customer_edit_context(customer: Customer) -> dict:
    """Returns the edit modal context for a single customer."""
    row = customer_row(customer)
    row.update(
        {
            "address": customer.address or "",
            "contact_number": customer.contact_number or "",
        }
    )
    return {"customer": row}
