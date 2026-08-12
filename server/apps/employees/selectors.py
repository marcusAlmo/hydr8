"""Read-side selectors for the Employees & Users pages.

Selectors return the exact context shapes consumed by
``employees/employees_directory.html`` and its partials.  They enforce
row-level tenant scoping (RLS) on every queryset.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.utils.timezone import localtime

from apps.customers.selectors import _display_id as _customer_display_id
from apps.remittance.models import RemittanceRiderProductLine, RiderCredit
from apps.users.models import Role, User
from apps.users.presentation import avatar_classes, initials

if TYPE_CHECKING:
    from apps.users.models import User as UserType

logger = logging.getLogger(__name__)

_MODULES = ["Remittance", "Customers", "Products", "Users", "Reports"]
PER_PAGE = 25

# ---------------------------------------------------------------------------
# Accent colour mapping for summary/stat cards.
# Maps the ``accent`` key in a stat dict to the Tailwind classes used in the
# template (border-top colour + icon colour). Kept here so both the employees
# views and the users edit-submit view can render stat cards consistently
# without duplicating the mapping.
# ---------------------------------------------------------------------------
_ACCENT_CLASSES = {
    "primary": {"border": "border-t-primary", "icon": "text-primary"},
    "warning": {"border": "border-t-[#D97706]", "icon": "text-[#D97706]"},
    "error": {"border": "border-t-error", "icon": "text-error"},
    "tertiary": {"border": "border-t-tertiary", "icon": "text-tertiary"},
}


def _apply_stat_accents(stats: list[dict]) -> None:
    """Mutate stat dicts in place, adding ``border_class`` and ``icon_class``."""
    for stat in stats:
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]

_ROLE_STYLE = {
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


def _format_peso(value) -> str:
    """Format a Decimal/float as a Philippine peso string."""
    try:
        return f"₱{float(value):,.2f}"
    except (TypeError, ValueError):
        return "₱0.00"


def _days_ago(dt) -> str:
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


def _user_qs(request_user: "UserType"):
    """Tenant-scoped queryset of active (not soft-deleted) users."""
    qs = User.objects.filter(deleted_at__isnull=True)
    if not request_user.is_superuser and request_user.company_id is not None:
        qs = qs.filter(company_id=request_user.company_id)
    return qs


def _user_status(user: User) -> str:
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


def _status_style(status: str) -> tuple[str, str]:
    """Returns (pill_class, dot_class) for a status string."""
    return {
        "active": ("bg-tertiary/10 text-tertiary", "bg-tertiary"),
        "onboarding": ("bg-[#D97706]/10 text-[#D97706]", "bg-[#D97706]"),
        "inactive": ("bg-error/10 text-error", "bg-error"),
    }.get(status, ("bg-tertiary/10 text-tertiary", "bg-tertiary"))


def _pin_style(user: User) -> tuple[str, str, str]:
    """Returns (status, label, icon_class) for the PIN security indicator."""
    if user.pin:
        return "set", "Set", "text-tertiary"
    return "not_set", "Not Set", "text-[#D97706] bg-[#D97706]/10"


def _role_badge_class(role_name: str) -> str:
    return {
        "Admin": "bg-primary/10 text-primary border-primary/20",
        "Driver": "bg-tertiary/10 text-tertiary border-tertiary/20",
        "Staff": "bg-secondary/10 text-secondary border-secondary/20",
    }.get(role_name, "bg-surface/10 text-on-surface-variant border-outline-variant/20")


def _user_row(user: User) -> dict:
    """Converts a ``User`` into the directory row shape."""
    status = _user_status(user)
    status_class, status_dot_class = _status_style(status)
    pin_status, pin_label, pin_class = _pin_style(user)
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
        "role_badge_class": _role_badge_class(role_name),
        "status": status,
        "status_label": status.title() if status != "onboarding" else "Onboarding",
        "status_class": status_class,
        "status_dot_class": status_dot_class,
        "last_login": _days_ago(user.last_login),
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


def _directory_stats(users_qs):
    active = users_qs.filter(is_active=True, deactivated_at__isnull=True)
    return [
        {
            "key": "active_users",
            "label": "Active Users",
            "value": f"{active.count():,}",
            "value_size": "4xl",
            "icon": "badge",
            "accent": "primary",
            "col_span": "md:col-span-4",
        },
        {
            "key": "active_riders",
            "label": "Active Riders",
            "value": f"{active.filter(role__name='Driver').count():,}",
            "value_size": "4xl",
            "icon": "two_wheeler",
            "accent": "warning",
            "col_span": "md:col-span-4",
        },
        {
            "key": "active_staffs",
            "label": "Active Staffs",
            "value": f"{active.filter(role__name='Staff').count():,}",
            "value_size": "4xl",
            "icon": "work",
            "accent": "tertiary",
            "col_span": "md:col-span-4",
        },
    ]


def _directory_filters(users_qs):
    total = users_qs.count()
    return [
        {"label": "All", "count": total, "active": True},
        {"label": "Admins", "count": users_qs.filter(role__name="Admin").count(), "active": False},
        {"label": "Staff", "count": users_qs.filter(role__name="Staff").count(), "active": False},
        {"label": "Drivers", "count": users_qs.filter(role__name="Driver").count(), "active": False},
        {
            "label": "Inactive",
            "count": users_qs.exclude(is_active=True, deactivated_at__isnull=True).count(),
            "active": False,
        },
    ]


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


def _pagination(total: int) -> dict:
    """Legacy fake pagination — used only by the full page render (small datasets)."""
    return {
        "showing_from": 1 if total else 0,
        "showing_to": total,
        "total": total,
        "total_display": f"{total:,}",
        "current_page": 1,
        "total_pages": 1 if total else 1,
    }


def _permission_rows(role: Role) -> list[dict]:
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


def _role_card(request_user: "UserType", role: Role) -> dict:
    """Converts a ``Role`` into the roles-permissions card shape."""
    style = _ROLE_STYLE.get(role.name, _ROLE_STYLE["Staff"])
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
        "permissions": _permission_rows(role),
    }


def _driver_detail_context(request_user: "UserType", user: User) -> dict:
    """Builds the driver expanded report with real remittance + credit data."""
    today = timezone.now().date()
    start = today - timedelta(days=29)

    product_lines = (
        RemittanceRiderProductLine.objects
        .for_user(request_user)
        .filter(
            remittance_rider__rider=user,
            remittance_rider__remittance__date__gte=start,
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
        commissions_daily.append(
            {
                "date": date_label,
                "units": entry["units"],
                "rate": f"₱{avg_rate:.2f}",
                "amount": _format_peso(commission),
                "amount_raw": commission,
            }
        )
        performance_trend.append({"date": date_label, "units": entry["units"]})
        commission_trend.append({"date": date_label, "cumulative": round(cumulative, 2)})

    total_commission = round(sum(c["amount_raw"] for c in commissions_daily), 2)
    total_units = sum(c["units"] for c in commissions_daily)
    days_count = len(commissions_daily) or 1
    avg_daily = round(total_commission / days_count, 2)

    unpaid_credits = (
        RiderCredit.objects
        .for_user(request_user)
        .filter(rider=user, is_repaid=False)
        .select_related("customer")
    )

    debts_handled = []
    for rc in unpaid_credits:
        days_overdue = (today - rc.created_at.date()).days
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
        customer = rc.customer
        customer_id = _customer_display_id(customer) if customer else "N/A"
        customer_name = customer.name if customer else rc.recipient_name
        debts_handled.append(
            {
                "customer_name": customer_name,
                "customer_id": customer_id,
                "amount": _format_peso(rc.amount),
                "amount_raw": float(rc.amount),
                "date": rc.created_at.strftime("%b %d, %Y"),
                "status": status,
                "status_label": status_label,
                "status_class": status_class,
                "row_border": row_border,
                "days_overdue": days_overdue,
            }
        )

    debts_sum = round(sum(d["amount_raw"] for d in debts_handled), 2)
    debts_outstanding = debts_sum

    trends_seed = json.dumps(
        {
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
                "value": _format_peso(total_commission),
                "value_size": "2xl",
                "subtitle": f"{total_units} units delivered",
                "icon": "payments",
                "accent": "tertiary",
                "col_span": "md:col-span-4",
            },
            {
                "key": "avg_daily",
                "label": "Avg Daily Commission",
                "value": _format_peso(avg_daily),
                "value_size": "2xl",
                "subtitle": f"Over {days_count} days",
                "icon": "trending_up",
                "accent": "primary",
                "col_span": "md:col-span-4",
            },
            {
                "key": "debts_outstanding",
                "label": "Outstanding Debts Handled",
                "value": _format_peso(debts_outstanding),
                "value_size": "2xl",
                "subtitle": f"{len(debts_handled)} customers, {_format_peso(debts_sum)} total",
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
        "debts_sum": _format_peso(debts_sum),
        "debts_outstanding_amount": _format_peso(debts_outstanding),
    }


def _staff_detail_context() -> dict:
    """Builds the staff expanded report (currently minimal real data)."""
    return {
        "is_staff": True,
        "staff_stats": [],
        "debts_assigned": [],
        "debts_sum": "₱0.00",
        "debts_outstanding_amount": "₱0.00",
    }


def _user_profile(user: User) -> dict:
    """Builds the common profile header shared by all role detail views."""
    row = _user_row(user)
    row["user_uuid"] = str(user.id)
    return row


def get_employee_directory_context(
    request_user: "UserType",
    query: str = "",
    page: int = 1,
) -> dict:
    """Returns the full context for the Employees & Users directory page.

    When ``query`` is non-empty, filters by first_name, last_name, or username
    using ``__icontains``. Uses real pagination (PER_PAGE=25).
    """
    users_qs = _user_qs(request_user)

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

    users = [_user_row(u) for u in page_obj.object_list]

    stats = _directory_stats(_user_qs(request_user))
    _apply_stat_accents(stats)

    return {
        "today_date": timezone.now().strftime("%A, %b %d, %Y"),
        "stats": stats,
        "filters": _directory_filters(_user_qs(request_user)),
        "users": users,
        "pagination": _pagination_from_page(page_obj),
        "search_query": query,
    }


def get_roles_permissions_context(request_user: "UserType") -> dict:
    """Returns the roles & permissions tab context."""
    roles = [
        _role_card(request_user, role)
        for role in Role.objects.for_user(request_user).active()
    ]
    _ROLE_ORDER = {"admin": 0, "staff": 1, "driver": 2}
    roles.sort(key=lambda r: _ROLE_ORDER.get(r["key"], 99))
    return {
        "modules": _MODULES,
        "roles": roles,
    }


def get_user_detail_context(request_user: "UserType", user_id: str) -> dict | None:
    """Returns the expanded report context for a single user, or ``None``."""
    target = _user_qs(request_user).filter(id=user_id).first()
    if target is None:
        return None

    profile = _user_profile(target)
    role_name = (target.role.name if target.role else "—").lower()
    context: dict = {"profile": profile, "role": target.role.name if target.role else "—"}

    if role_name == "driver":
        context.update(_driver_detail_context(request_user, target))
        _apply_stat_accents(context.get("driver_stats", []))
    elif role_name == "staff":
        context.update(_staff_detail_context())
        _apply_stat_accents(context.get("staff_stats", []))
    else:
        context.update({"is_admin": True})

    return context
