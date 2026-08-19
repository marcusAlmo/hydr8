"""Presentation layer for the Employees & Users pages.

This module contains the template-shaped formatting/dict-shaping helpers
that were previously mixed into ``selectors_employees.py``.  Selectors now
return *raw* query data; the functions here convert that raw data into the
exact context shapes consumed by ``employees/employees_directory.html``
and its partials.

No business logic, tenant scoping, or authorization lives here — those
concerns remain in the selectors and views.
"""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from django.utils.timezone import localtime
from django.utils import timezone

from apps.customers.presentation import display_id as _customer_display_id
from apps.users.presentation import avatar_classes, initials
from apps.users.selectors_employees import _MODULES

if TYPE_CHECKING:
    from apps.users.models import Role, User

# ---------------------------------------------------------------------------
# Accent colour mapping for summary/stat cards.
# Maps the ``accent`` key in a stat dict to the Tailwind classes used in the
# template (border-top colour + icon colour). Kept here so both the employees
# views and the users edit-submit view can render stat cards consistently
# without duplicating the mapping.
# ---------------------------------------------------------------------------
ACCENT_CLASSES = {
    "primary": {"border": "border-t-primary", "icon": "text-primary"},
    "warning": {"border": "border-t-[#D97706]", "icon": "text-[#D97706]"},
    "error": {"border": "border-t-error", "icon": "text-error"},
    "tertiary": {"border": "border-t-tertiary", "icon": "text-tertiary"},
}


def apply_stat_accents(stats: list[dict]) -> None:
    """Mutate stat dicts in place, adding ``border_class`` and ``icon_class``."""
    for stat in stats:
        accent = ACCENT_CLASSES.get(stat["accent"], ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]


ROLE_STYLE = {
    "Admin": {
        "accent": "tertiary",
        "border": "border-t-tertiary",
        "icon_bg": "bg-tertiary-container/20",
        "icon_class": "text-tertiary",
        "icon": "shield_person",
    },
    "Staff": {
        "accent": "secondary",
        "border": "border-t-secondary",
        "icon_bg": "bg-secondary-container/20",
        "icon_class": "text-secondary",
        "icon": "work",
    },
    "Driver": {
        "accent": "warning",
        "border": "border-t-[#D97706]",
        "icon_bg": "bg-[#D97706]/10",
        "icon_class": "text-[#D97706]",
        "icon": "two_wheeler",
    },
}


def format_peso(value) -> str:
    """Format a Decimal/float as a Philippine peso string."""
    try:
        if isinstance(value, Decimal):
            return f"₱{value:,.2f}"
        return f"₱{Decimal(str(value)):,.2f}"
    except (TypeError, ValueError, InvalidOperation):
        return "₱0.00"


def days_ago_text(dt) -> str:
    """Human-friendly relative time string with a short timestamp."""
    if not dt:
        return "Never"
    now = timezone.now()
    local = localtime(dt)
    if local.date() == now.date():
        return f"Today {local.strftime('%H:%M')}"
    if local.date() == (now.date() - timedelta(days=1)):
        return f"Yesterday {local.strftime('%H:%M')}"
    days = (now - dt).days
    if 0 <= days < 7:
        return f"{days} days ago"
    return local.strftime("%b %d, %Y")


def user_status(user: "User") -> str:
    """
    Derives the UI status for a user.

      - ``inactive``: manually deactivated
      - ``onboarding``: active but no PIN set yet
      - ``active``: active with a PIN
    """
    if not user.is_active or user.deactivated_at is not None:
        return "inactive"
    if not user.pin:
        return "onboarding"
    return "active"


def status_style(status: str) -> tuple[str, str]:
    """Returns (pill_class, dot_class) for a status string."""
    return {
        "active": ("bg-tertiary/10 text-tertiary", "bg-tertiary"),
        "onboarding": ("bg-[#D97706]/10 text-[#D97706]", "bg-[#D97706]"),
        "inactive": ("bg-error/10 text-error", "bg-error"),
    }.get(status, ("bg-tertiary/10 text-tertiary", "bg-tertiary"))


def pin_style(user: "User") -> tuple[str, str, str]:
    """Returns (status, label, icon_class) for the PIN security indicator."""
    if user.pin:
        return "set", "Set", "text-tertiary"
    return "not_set", "Not Set", "text-[#D97706] bg-[#D97706]/10"


def role_badge_class(role_name: str) -> str:
    return {
        "Admin": "bg-primary/10 text-primary border-primary/20",
        "Driver": "bg-tertiary/10 text-tertiary border-tertiary/20",
        "Staff": "bg-secondary/10 text-secondary border-secondary/20",
    }.get(role_name, "bg-surface/10 text-on-surface-variant border-outline-variant/20")


def user_row(user: "User") -> dict:
    """Converts a ``User`` into the directory row shape."""
    status = user_status(user)
    status_class, status_dot_class = status_style(status)
    pin_status, pin_label, pin_class = pin_style(user)
    pin_icon = "check_circle" if pin_status == "set" else "vpn_key_alert"
    bg, text = avatar_classes(user)
    role_name = user.role.name if user.role else "—"
    return {
        "id": str(user.id),
        "name": user.full_name,
        "initials": initials(user),
        "username": f"@{user.username}",
        "avatar_bg": bg,
        "avatar_text": text,
        "role": role_name,
        "role_badge_class": role_badge_class(role_name),
        "status": status,
        "status_label": status.title() if status != "onboarding" else "Onboarding",
        "status_class": status_class,
        "status_dot_class": status_dot_class,
        "last_login": days_ago_text(user.last_login),
        "last_login_class": "text-outline" if status == "inactive" else "text-on-surface-variant",
        "pin_status": pin_status,
        "pin_label": pin_label,
        "pin_class": pin_class,
        "pin_icon": pin_icon,
        "row_border": {
            "active": "border-l-transparent",
            "onboarding": "border-l-[#D97706]",
            "inactive": "border-l-error",
        }.get(status, "border-l-transparent"),
        "row_opacity": "opacity-70" if status == "inactive" else "",
        "name_class": "line-through decoration-outline" if status == "inactive" else "",
        "actions": "resend" if status == "onboarding" else "edit",
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


def pagination(total: int) -> dict:
    """Legacy fake pagination — used only by the full page render (small datasets)."""
    return {
        "showing_from": 1 if total else 0,
        "showing_to": total,
        "total": total,
        "total_display": f"{total:,}",
        "current_page": 1,
        "total_pages": 1 if total else 1,
    }


def permission_rows(role: "Role") -> list[dict]:
    """Builds the RWUD permission matrix for a single role."""
    perms = {p.action: p for p in role.permissions.all()}
    rows = []
    for module in _MODULES:
        perm = perms.get(module)
        if perm:
            rows.append(
                {
                    "module": module,
                    "read": perm.can_read,
                    "write": perm.can_write,
                    "update": perm.can_update,
                    "delete": perm.can_delete,
                }
            )
        else:
            rows.append(
                {
                    "module": module,
                    "read": False,
                    "write": False,
                    "update": False,
                    "delete": False,
                }
            )
    return rows


def role_card(role: "Role") -> dict:
    """Converts a ``Role`` into the roles-permissions card shape."""
    style = ROLE_STYLE.get(role.name, ROLE_STYLE["Staff"])
    return {
        "key": role.name.lower(),
        "name": role.name,
        "description": role.description or "",
        "user_count": role.user_set.filter(deleted_at__isnull=True).count(),
        "icon": style["icon"],
        "accent": style["accent"],
        "border_class": style["border"],
        "icon_bg": style["icon_bg"],
        "icon_class": style["icon_class"],
        "permissions": permission_rows(role),
    }


def user_profile(user: "User") -> dict:
    """Builds the common profile header shared by all role detail views."""
    row = user_row(user)
    row["user_uuid"] = str(user.id)
    return row


# ---------------------------------------------------------------------------
# Dict-shaping helpers for split selector/presentation functions.
# These convert the *raw* data returned by selectors into the final template
# context shapes.
# ---------------------------------------------------------------------------

def build_directory_stats(counts: dict) -> list[dict]:
    """Shapes the directory summary stat-card dicts from raw counts."""
    active_users_count = counts["active_users"]
    active_riders_count = counts["active_riders"]
    active_staffs_count = counts["active_staffs"]
    return [
        {
            "key": "active_users",
            "label": "Active Users",
            "value": f"{active_users_count:,}",
            "raw_value": active_users_count,
            "value_prefix": "",
            "value_decimals": 0,
            "value_size": "4xl",
            "icon": "badge",
            "accent": "primary",
            "col_span": "md:col-span-4",
        },
        {
            "key": "active_riders",
            "label": "Active Riders",
            "value": f"{active_riders_count:,}",
            "raw_value": active_riders_count,
            "value_prefix": "",
            "value_decimals": 0,
            "value_size": "4xl",
            "icon": "two_wheeler",
            "accent": "warning",
            "col_span": "md:col-span-4",
        },
        {
            "key": "active_staffs",
            "label": "Active Staffs",
            "value": f"{active_staffs_count:,}",
            "raw_value": active_staffs_count,
            "value_prefix": "",
            "value_decimals": 0,
            "value_size": "4xl",
            "icon": "work",
            "accent": "tertiary",
            "col_span": "md:col-span-4",
        },
    ]


def build_directory_filters(counts: dict) -> list[dict]:
    """Shapes the directory filter-chip dicts from raw per-role counts."""
    return [
        {"label": "All", "count": counts["total"], "active": True},
        {"label": "Admins", "count": counts["Admins"], "active": False},
        {"label": "Staff", "count": counts["Staff"], "active": False},
        {"label": "Drivers", "count": counts["Drivers"], "active": False},
        {"label": "Inactive", "count": counts["Inactive"], "active": False},
    ]


def build_driver_detail_context(data: dict) -> dict:
    """Builds the driver expanded report context from raw selector data.

    The trend seed covers a 90-day window so the client-side date-range
    filter (7D/14D/30D/custom) always has data to slice.  Each entry
    carries an ``iso_date`` (YYYY-MM-DD) so the Alpine component can
    filter by real calendar date instead of by array index — the prior
    index-based slicing broke because the seed is sparse (one entry per
    day that actually has a remittance, not one per calendar day).

    The three stat cards remain a fixed 30-day summary (computed from
    the 30-day subset of the same query) so their "(30D)" labels stay
    accurate regardless of the active chart filter.
    """
    by_date: dict = data["by_date"]
    today = data["today"]
    total_commission = data["total_commission"]
    total_units = data["total_units"]
    days_count = data["days_count"]
    avg_daily = data["avg_daily"]
    open_credit_lines = data["open_credit_lines"]
    debts_sum = data["debts_sum"]
    distinct_customers = data["distinct_customers"]

    commissions_daily = []
    performance_trend = []
    commission_trend = []
    cumulative = 0.0

    for d in sorted(by_date.keys()):
        entry = by_date[d]
        avg_rate = (
            entry["rate_total"] / entry["rate_count"]
            if entry["rate_count"]
            else Decimal("0.00")
        )
        commission = float(entry["commission"])
        cumulative += commission
        date_label = d.strftime("%b %d")
        iso_date = d.isoformat()
        commissions_daily.append(
            {
                "date": date_label,
                "iso_date": iso_date,
                "units": entry["units"],
                "rate": f"₱{avg_rate:.2f}",
                "amount": format_peso(entry["commission"]),
                "amount_raw": commission,
            }
        )
        performance_trend.append({"date": date_label, "iso_date": iso_date, "units": entry["units"]})
        commission_trend.append({"date": date_label, "iso_date": iso_date, "cumulative": round(cumulative, 2)})

    debts_handled = []
    for line in open_credit_lines:
        outstanding = line.qty_remaining * line.unit_price_snapshot
        days_overdue = (today - line.transaction_date).days
        status = "overdue" if days_overdue > 7 else "pending"
        status_label = "Overdue" if status == "overdue" else "Pending"
        status_class = (
            "bg-error/10 text-error"
            if status == "overdue"
            else "bg-[#D97706]/10 text-[#D97706]"
        )
        row_border = (
            "border-l-error" if status == "overdue" else "border-l-[#D97706]"
        )
        customer = line.customer
        customer_id = _customer_display_id(customer) if customer else "N/A"
        customer_name = customer.name if customer else "Unknown"
        debts_handled.append(
            {
                "customer_name": customer_name,
                "customer_id": customer_id,
                "amount": format_peso(outstanding),
                "amount_raw": float(outstanding),
                "date": line.transaction_date.strftime("%b %d, %Y"),
                "status": status,
                "status_label": status_label,
                "status_class": status_class,
                "row_border": row_border,
                "days_overdue": days_overdue,
            }
        )

    trends_seed = json.dumps(
        {
            "dates": [p["iso_date"] for p in performance_trend],
            "labels": [p["date"] for p in performance_trend],
            "performance": [p["units"] for p in performance_trend],
            "commissions": [c["cumulative"] for c in commission_trend],
        }
    )

    return {
        "is_driver": True,
        "driver_stats": [
            {
                "key": "total_commissions",
                "label": "Commissions Paid (30D)",
                "value": format_peso(total_commission),
                "raw_value": float(total_commission),
                "value_prefix": "₱",
                "value_decimals": 2,
                "value_size": "2xl",
                "subtitle": f"{total_units} units delivered",
                "icon": "payments",
                "accent": "tertiary",
                "col_span": "md:col-span-4",
            },
            {
                "key": "avg_daily",
                "label": "Avg Daily Commission",
                "value": format_peso(avg_daily),
                "raw_value": float(avg_daily),
                "value_prefix": "₱",
                "value_decimals": 2,
                "value_size": "2xl",
                "subtitle": f"Over {days_count} days",
                "icon": "trending_up",
                "accent": "primary",
                "col_span": "md:col-span-4",
            },
            {
                "key": "debts_outstanding",
                "label": "Outstanding Debts Handled",
                "value": format_peso(debts_sum),
                "raw_value": float(debts_sum),
                "value_prefix": "₱",
                "value_decimals": 2,
                "value_size": "2xl",
                "subtitle": (
                    f"{distinct_customers} customer"
                    f"{'s' if distinct_customers != 1 else ''}, "
                    f"{len(debts_handled)} open debt"
                    f"{'s' if len(debts_handled) != 1 else ''}, "
                    f"{format_peso(debts_sum)} total"
                ),
                "icon": "dangerous",
                "accent": "error",
                "col_span": "md:col-span-4",
            },
        ],
        "commissions_daily": commissions_daily,
        "commissions_daily_json": json.dumps(commissions_daily),
        "performance_trend": performance_trend,
        "commission_trend": commission_trend,
        "trends_seed": trends_seed,
        "debts_handled": debts_handled,
        "debts_sum": format_peso(debts_sum),
        "debts_outstanding_amount": format_peso(debts_sum),
    }


def build_staff_detail_context(data: dict) -> dict:
    """Builds the staff expanded report context from raw selector data."""
    daily_rate = data["daily_rate"]
    staff_stats = [
        {
            "key": "daily_rate",
            "label": "Daily Rate",
            "value": format_peso(daily_rate),
            "raw_value": float(daily_rate),
            "value_prefix": "₱",
            "value_decimals": 2,
            "value_size": "2xl",
            "subtitle": "Fixed daily salary",
            "icon": "payments",
            "accent": "tertiary",
            "col_span": "md:col-span-12",
        },
    ]
    return {
        "is_staff": True,
        "staff_stats": staff_stats,
        "daily_rate": format_peso(daily_rate),
        "debts_assigned": [],
        "debts_sum": "₱0.00",
        "debts_outstanding_amount": "₱0.00",
    }


# ---------------------------------------------------------------------------
# Top-level context builders — compose raw selector data into the final
# template context dicts consumed by the views.
# ---------------------------------------------------------------------------

def build_employee_directory_context(data: dict) -> dict:
    """Shapes the full context for the Employees & Users directory page."""
    users = [user_row(u) for u in data["users"]]

    stats = build_directory_stats(data["stats_counts"])
    apply_stat_accents(stats)

    return {
        "today_date": timezone.localtime().strftime("%A, %b %d, %Y"),
        "stats": stats,
        "filters": build_directory_filters(data["filter_counts"]),
        "users": users,
        "pagination": pagination_from_page(data["page_obj"]),
        "search_query": data["query"],
    }


def build_roles_permissions_context(data: dict) -> dict:
    """Shapes the roles & permissions tab context."""
    roles = [role_card(role) for role in data["roles"]]
    _ROLE_ORDER = {"admin": 0, "staff": 1, "driver": 2}
    roles.sort(key=lambda r: _ROLE_ORDER.get(r["key"], 99))
    return {
        "modules": _MODULES,
        "roles": roles,
    }


def build_user_detail_context(data: dict) -> dict:
    """Shapes the expanded report context for a single user."""
    target: "User" = data["target"]
    role_name = data["role_name"]

    profile = user_profile(target)
    context: dict = {"profile": profile, "role": target.role.name if target.role else "—"}

    if role_name == "driver":
        context.update(build_driver_detail_context(data["driver_data"]))
        apply_stat_accents(context.get("driver_stats", []))
    elif role_name == "staff":
        context.update(build_staff_detail_context(data["staff_data"]))
        apply_stat_accents(context.get("staff_stats", []))
    else:
        context.update({"is_admin": True})

    return context
