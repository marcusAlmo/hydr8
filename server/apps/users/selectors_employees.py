"""Read-side selectors for the Employees & Users pages.

Selectors return *raw* query data — no template-shaped formatting.  The
presentation layer (``presentation_employees.py``) converts this raw data
into the context shapes consumed by the templates.

All querysets enforce row-level tenant scoping (RLS) via ``_user_qs``.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from apps.customers.models import CreditLine
from apps.remittance.models import RemittanceRiderProductLine
from apps.users.models import Role, User

if TYPE_CHECKING:
    from apps.users.models import User as UserType

logger = logging.getLogger(__name__)

_MODULES = ["Remittance", "Customers", "Products", "Users", "Reports"]
PER_PAGE = 25


def _user_qs(request_user: "UserType"):
    """Tenant-scoped queryset of active (not soft-deleted) users."""
    qs = User.objects.filter(deleted_at__isnull=True)
    if not request_user.is_superuser and request_user.company_id is not None:
        qs = qs.filter(company_id=request_user.company_id)
    return qs


# ---------------------------------------------------------------------------
# Raw data selectors — return plain dicts/lists, no formatting.
# ---------------------------------------------------------------------------

def _directory_stats_counts(users_qs) -> dict:
    """Raw counts for the directory summary stat cards."""
    active = users_qs.filter(is_active=True, deactivated_at__isnull=True)
    return {
        "active_users": active.count(),
        "active_riders": active.filter(role__name='Driver').count(),
        "active_staffs": active.filter(role__name='Staff').count(),
    }


def _directory_filter_counts(users_qs) -> dict:
    """Raw per-role counts for the directory filter chips."""
    total = users_qs.count()
    return {
        "total": total,
        "Admins": users_qs.filter(role__name="Admin").count(),
        "Staff": users_qs.filter(role__name="Staff").count(),
        "Drivers": users_qs.filter(role__name="Driver").count(),
        "Inactive": users_qs.exclude(is_active=True, deactivated_at__isnull=True).count(),
    }


def _driver_detail_data(request_user: "UserType", user: User) -> dict:
    """Raw driver report data: product-line aggregates, stat summary, open debts.

    The trend seed covers a 90-day window so the client-side date-range
    filter (7D/14D/30D/custom) always has data to slice.

    The three stat cards remain a fixed 30-day summary (computed from
    the 30-day subset of the same query) so their "(30D)" labels stay
    accurate regardless of the active chart filter.
    """
    today = timezone.localdate()
    # 90-day window for the trend seed (charts + daily table).
    seed_start = today - timedelta(days=89)
    # 30-day window for the summary stat cards.
    stat_start = today - timedelta(days=29)

    product_lines = (
        RemittanceRiderProductLine.objects
        .for_user(request_user)
        .filter(
            remittance_rider__rider=user,
            remittance_rider__remittance__date__gte=seed_start,
            remittance_rider__remittance__date__lte=today,
        )
        .select_related("remittance_rider__remittance", "product")
        .order_by("remittance_rider__remittance__date")
    )

    by_date: dict[date, dict] = {}
    for line in product_lines:
        d = line.remittance_rider.remittance.date
        entry = by_date.setdefault(
            d,
            {
                "units": 0,
                "commission": Decimal("0.00"),
                "rate_total": Decimal("0.00"),
                "rate_count": 0,
            },
        )
        entry["units"] += line.qty_sold
        entry["commission"] += line.subtotal_commission
        if line.commission_rate_snapshot:
            entry["rate_total"] += line.commission_rate_snapshot
            entry["rate_count"] += 1

    # --- 30-day stat-card summary (fixed window, independent of chart filter)
    stat_commission = 0.0
    stat_units = 0
    stat_days = 0
    for d, entry in by_date.items():
        if d < stat_start:
            continue
        stat_commission += float(entry["commission"])
        stat_units += entry["units"]
        stat_days += 1
    total_commission = round(stat_commission, 2)
    total_units = stat_units
    days_count = stat_days or 1
    avg_daily = round(stat_commission / days_count, 2)

    # Outstanding credit lines (debts) attributed to this user via
    # ``care_of``.  These are the records created by the "Record Debt"
    # modal on the Customers page — the single source of truth for
    # customer debt in the UI.  ``RiderCredit`` is a legacy remittance
    # concept that is no longer populated through the UI, so querying it
    # here would always return an empty list.
    open_credit_lines = list(
        CreditLine.objects
        .for_user(request_user)
        .filter(care_of=user, qty_remaining__gt=0)
        .select_related("customer", "product")
        .order_by("-transaction_date", "-created_at")
    )

    debts_sum = round(
        sum(
            float(line.qty_remaining * line.unit_price_snapshot)
            for line in open_credit_lines
        ),
        2,
    )
    # Distinct customers with at least one open credit line attributed to
    # this driver — avoids miscounting when one customer has multiple
    # open lines (e.g. two products credited on different dates).
    distinct_customers = (
        len({line.customer_id for line in open_credit_lines})
    )

    return {
        "today": today,
        "by_date": by_date,
        "total_commission": total_commission,
        "total_units": total_units,
        "days_count": days_count,
        "avg_daily": avg_daily,
        "open_credit_lines": open_credit_lines,
        "debts_sum": debts_sum,
        "distinct_customers": distinct_customers,
    }


def _staff_detail_data(user: User) -> dict:
    """Raw staff report data: daily rate."""
    return {
        "daily_rate": user.daily_rate or Decimal("0.00"),
    }


def get_employee_directory_data(
    request_user: "UserType",
    query: str = "",
    page: int = 1,
) -> dict:
    """Returns raw data for the Employees & Users directory page.

    When ``query`` is non-empty, filters by first_name, last_name, or username
    using ``__icontains``. Uses real pagination (PER_PAGE=25).
    """
    users_qs = _user_qs(request_user).select_related('role')

    # Apply search filter
    query = (query or "").strip()
    if query:
        users_qs = users_qs.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(username__icontains=query)
        )

    users_qs = users_qs.order_by("first_name", "last_name")

    # Real pagination
    paginator = Paginator(users_qs, PER_PAGE)
    page_obj = paginator.get_page(page)

    base_qs = _user_qs(request_user)

    return {
        "page_obj": page_obj,
        "users": list(page_obj.object_list),
        "stats_counts": _directory_stats_counts(base_qs),
        "filter_counts": _directory_filter_counts(base_qs),
        "query": query,
    }


def get_roles_permissions_data(request_user: "UserType") -> dict:
    """Returns raw data for the roles & permissions tab."""
    roles = list(
        Role.objects.for_user(request_user)
        .active()
        .prefetch_related('permissions')
    )
    return {
        "roles": roles,
    }


def get_user_detail_data(request_user: "UserType", user_id: str) -> dict | None:
    """Returns raw data for a single user's expanded report, or ``None``."""
    target = _user_qs(request_user).filter(id=user_id).select_related('role').first()
    if target is None:
        return None

    role_name = (target.role.name if target.role else "—").lower()

    data: dict = {"target": target, "role_name": role_name}

    if role_name == "driver":
        data["driver_data"] = _driver_detail_data(request_user, target)
    elif role_name == "staff":
        data["staff_data"] = _staff_detail_data(target)

    return data
