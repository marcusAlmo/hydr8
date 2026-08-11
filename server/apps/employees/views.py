import json
import math
from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit


# ---------------------------------------------------------------------------
# Accent colour mapping for summary cards.
# Maps the `accent` key in a stat dict to the Tailwind classes used in the
# template (border-top colour + icon colour).
# ---------------------------------------------------------------------------
_ACCENT_CLASSES = {
    "primary": {"border": "border-t-primary", "icon": "text-primary"},
    "warning": {"border": "border-t-[#D97706]", "icon": "text-[#D97706]"},
    "error": {"border": "border-t-error", "icon": "text-error"},
    "tertiary": {"border": "border-t-tertiary", "icon": "text-tertiary"},
}


def _mock_directory_data() -> dict:
    """
    Mock data for the Employees & Users Directory tab.

    Temporary fixture used to prototype the user-management layout, summary
    cards, filter chips, and the users table with role/status/PIN indicators
    before backend services are implemented.  Field shape mirrors the
    ``apps.users.models.User`` model:
      username, first_name, last_name, email, pin, role, is_active,
      deactivated_at, last_login, date_joined

    Replace this function with real selectors once the User service layer is
    ready — the template already consumes these context keys.
    """
    now = datetime.now()

    return {
        # --- Top bar ---
        "today_date": now.strftime("%A, %b %d, %Y"),

        # --- Summary cards (asymmetric grid) ---
        # Only counts we can derive reliably from role + is_active flags.
        # "Active Today" and "Pending PIN Setup" are omitted because we
        # cannot derive them accurately from the current mock data shape.
        "stats": [
            {
                "key": "active_users",
                "label": "Active Users",
                "value": "12",
                "value_size": "4xl",
                "icon": "badge",
                "accent": "primary",
                "col_span": "md:col-span-4",
            },
            {
                "key": "active_riders",
                "label": "Active Riders",
                "value": "4",
                "value_size": "4xl",
                "icon": "two_wheeler",
                "accent": "warning",
                "col_span": "md:col-span-4",
            },
            {
                "key": "active_staffs",
                "label": "Active Staffs",
                "value": "5",
                "value_size": "4xl",
                "icon": "work",
                "accent": "tertiary",
                "col_span": "md:col-span-4",
            },
        ],

        # --- Filter chips ---
        "filters": [
            {"label": "All", "count": 14, "active": True},
            {"label": "Admins", "count": 3, "active": False},
            {"label": "Staff", "count": 6, "active": False},
            {"label": "Drivers", "count": 5, "active": False},
            {"label": "Inactive", "count": 2, "active": False},
        ],

        # --- Users table ---
        # status: 'active' | 'onboarding' | 'inactive'
        # pin_status: 'set' | 'not_set' | 'revoked'
        "users": [
            {
                "id": "USR-001",
                "name": "Maria Santos",
                "initials": "MS",
                "username": "@maria.s",
                "avatar_bg": "bg-primary-container",
                "avatar_text": "text-on-primary-container",
                "role": "Admin",
                "role_badge_class": "bg-primary/10 text-primary border-primary/20",
                "status": "active",
                "status_label": "Active",
                "status_class": "bg-tertiary/10 text-tertiary",
                "status_dot_class": "bg-tertiary",
                "last_login": "Today 09:14",
                "last_login_class": "text-on-surface-variant",
                "pin_status": "set",
                "pin_label": "Set",
                "pin_class": "text-tertiary",
                "pin_icon": "check_circle",
                "row_border": "border-l-transparent",
                "row_opacity": "",
                "name_class": "",
                "actions": "edit",
            },
            {
                "id": "USR-002",
                "name": "Juan Dela Cruz",
                "initials": "JC",
                "username": "@juan.driver",
                "avatar_bg": "bg-tertiary-container",
                "avatar_text": "text-on-tertiary-container",
                "role": "Driver",
                "role_badge_class": "bg-tertiary/10 text-tertiary border-tertiary/20",
                "status": "active",
                "status_label": "Active",
                "status_class": "bg-tertiary/10 text-tertiary",
                "status_dot_class": "bg-tertiary",
                "last_login": "Today 08:42",
                "last_login_class": "text-on-surface-variant",
                "pin_status": "set",
                "pin_label": "Set",
                "pin_class": "text-tertiary",
                "pin_icon": "check_circle",
                "row_border": "border-l-transparent",
                "row_opacity": "",
                "name_class": "",
                "actions": "edit",
            },
            {
                "id": "USR-003",
                "name": "Roberto Santos",
                "initials": "RS",
                "username": "@rob.s",
                "avatar_bg": "bg-secondary-container",
                "avatar_text": "text-on-secondary-container",
                "role": "Staff",
                "role_badge_class": "bg-secondary/10 text-secondary border-secondary/20",
                "status": "active",
                "status_label": "Active",
                "status_class": "bg-tertiary/10 text-tertiary",
                "status_dot_class": "bg-tertiary",
                "last_login": "Yesterday 17:30",
                "last_login_class": "text-on-surface-variant",
                "pin_status": "set",
                "pin_label": "Set",
                "pin_class": "text-tertiary",
                "pin_icon": "check_circle",
                "row_border": "border-l-transparent",
                "row_opacity": "",
                "name_class": "",
                "actions": "edit",
            },
            {
                "id": "USR-004",
                "name": "Carla Reyes",
                "initials": "CR",
                "username": "@carla.r (New)",
                "avatar_bg": "bg-surface-dim",
                "avatar_text": "text-on-surface-variant",
                "role": "Driver",
                "role_badge_class": "bg-tertiary/10 text-tertiary border-tertiary/20",
                "status": "onboarding",
                "status_label": "Onboarding",
                "status_class": "bg-[#D97706]/10 text-[#D97706]",
                "status_dot_class": "bg-[#D97706]",
                "last_login": "Never",
                "last_login_class": "text-outline",
                "pin_status": "not_set",
                "pin_label": "Not Set",
                "pin_class": "text-[#D97706] bg-[#D97706]/10",
                "pin_icon": "vpn_key_alert",
                "row_border": "border-l-[#D97706]",
                "row_opacity": "",
                "name_class": "",
                "actions": "resend",
            },
            {
                "id": "USR-005",
                "name": "Pedro Lim",
                "initials": "PL",
                "username": "@pedro.staff",
                "avatar_bg": "bg-surface-dim",
                "avatar_text": "text-on-surface-variant",
                "role": "Staff",
                "role_badge_class": "bg-secondary/5 text-secondary border-secondary/10",
                "status": "inactive",
                "status_label": "Inactive",
                "status_class": "bg-error/10 text-error",
                "status_dot_class": "bg-error",
                "last_login": "3 days ago",
                "last_login_class": "text-outline",
                "pin_status": "revoked",
                "pin_label": "Revoked",
                "pin_class": "text-outline",
                "pin_icon": "lock",
                "row_border": "border-l-error",
                "row_opacity": "opacity-70",
                "name_class": "line-through decoration-outline",
                "actions": "view",
            },
            {
                "id": "USR-006",
                "name": "Ana Tan",
                "initials": "AT",
                "username": "@ana.t",
                "avatar_bg": "bg-primary-container",
                "avatar_text": "text-on-primary-container",
                "role": "Admin",
                "role_badge_class": "bg-primary/10 text-primary border-primary/20",
                "status": "active",
                "status_label": "Active",
                "status_class": "bg-tertiary/10 text-tertiary",
                "status_dot_class": "bg-tertiary",
                "last_login": "Today 10:05",
                "last_login_class": "text-on-surface-variant",
                "pin_status": "set",
                "pin_label": "Set",
                "pin_class": "text-tertiary",
                "pin_icon": "check_circle",
                "row_border": "border-l-transparent",
                "row_opacity": "",
                "name_class": "",
                "actions": "edit",
            },
        ],

        # --- Pagination ---
        "pagination": {
            "showing_from": 1,
            "showing_to": 6,
            "total": 14,
            "total_display": "14",
            "current_page": 1,
            "total_pages": 3,
        },
    }


def _mock_roles_data() -> dict:
    """
    Mock data for the Roles & Permissions tab.

    Three role cards (Admin, Staff, Driver) each with a permission matrix
    showing read/write/update/delete access per module.  Mirrors the
    ``apps.users.models.Role`` and ``Permission`` models.

    Replace with real selectors once the role/permission service layer is
    ready — the template already consumes these context keys.
    """
    # Modules (rows of the permission matrix)
    modules = [
        "Remittance",
        "Customers",
        "Products",
        "Users",
        "Reports",
    ]

    # Permission flags per role per module.
    # Each entry: { module, read, write, update, delete }
    admin_perms = [
        {"module": "Remittance", "read": True, "write": True, "update": True, "delete": True},
        {"module": "Customers", "read": True, "write": True, "update": True, "delete": True},
        {"module": "Products", "read": True, "write": True, "update": True, "delete": True},
        {"module": "Users", "read": True, "write": True, "update": True, "delete": True},
        {"module": "Reports", "read": True, "write": True, "update": True, "delete": True},
    ]
    staff_perms = [
        {"module": "Remittance", "read": True, "write": True, "update": True, "delete": False},
        {"module": "Customers", "read": True, "write": True, "update": True, "delete": False},
        {"module": "Products", "read": True, "write": True, "update": False, "delete": False},
        {"module": "Users", "read": False, "write": False, "update": False, "delete": False},
        {"module": "Reports", "read": True, "write": False, "update": False, "delete": False},
    ]
    driver_perms = [
        {"module": "Remittance", "read": True, "write": True, "update": True, "delete": False},
        {"module": "Customers", "read": True, "write": False, "update": False, "delete": False},
        {"module": "Products", "read": False, "write": False, "update": False, "delete": False},
        {"module": "Users", "read": False, "write": False, "update": False, "delete": False},
        {"module": "Reports", "read": False, "write": False, "update": False, "delete": False},
    ]

    return {
        "modules": modules,
        "roles": [
            {
                "key": "admin",
                "name": "Admin",
                "description": "Full system access — manage users, roles, remittances, and all operational data.",
                "user_count": 3,
                "icon": "shield_person",
                "accent": "tertiary",
                "border_class": "border-t-tertiary",
                "icon_bg": "bg-tertiary-container/20",
                "icon_class": "text-tertiary",
                "permissions": admin_perms,
            },
            {
                "key": "staff",
                "name": "Staff",
                "description": "Day-to-day operations — process remittances, manage customers, update product inventory.",
                "user_count": 6,
                "icon": "work",
                "accent": "secondary",
                "border_class": "border-t-secondary",
                "icon_bg": "bg-secondary-container/20",
                "icon_class": "text-secondary",
                "permissions": staff_perms,
            },
            {
                "key": "driver",
                "name": "Driver",
                "description": "Delivery riders — submit daily remittances and view assigned customer routes.",
                "user_count": 5,
                "icon": "two_wheeler",
                "accent": "warning",
                "border_class": "border-t-[#D97706]",
                "icon_bg": "bg-[#D97706]/10",
                "icon_class": "text-[#D97706]",
                "permissions": driver_perms,
            },
        ],
    }


def _mock_user_detail_data(user_id: str) -> dict:
    """
    Mock per-user expanded report data for the user detail drawer.

    Returns role-specific data:
      - Driver:  daily commissions paid, performance trend (units sold),
                 commission trend, debts handled by this driver + sum
      - Staff:   debts assigned to / named after this staff member + sum
      - Admin:   basic profile only (no performance or debt data)

    The 14-day trend series are generated deterministically from the user_id
    so each driver shows a distinct but stable pattern across page reloads.

    Replace with real selectors once the remittance/credit-line service
    layer is ready — the template already consumes these context keys.
    """
    # --- User lookup from the directory mock ---
    directory = _mock_directory_data()
    user = next((u for u in directory["users"] if u["id"] == user_id), None)
    if user is None:
        raise Http404("User not found")

    # Deterministic seed from user_id for stable mock series
    seed = sum(ord(c) for c in user_id)

    # --- Common profile data ---
    profile = {
        "id": user["id"],
        "name": user["name"],
        "initials": user["initials"],
        "username": user["username"],
        "avatar_bg": user["avatar_bg"],
        "avatar_text": user["avatar_text"],
        "role": user["role"],
        "status": user["status"],
        "status_label": user["status_label"],
        "status_class": user["status_class"],
        "status_dot_class": user["status_dot_class"],
        "pin_status": user["pin_status"],
        "pin_label": user["pin_label"],
        "last_login": user["last_login"],
    }

    # --- Map mock user IDs to real User UUIDs for admin actions ---
    # The mock directory uses placeholder IDs (USR-001, etc.) for display.
    # Admin actions (generate temp password, edit user) need real UUIDs.
    # We map each mock user to a real username and look up the UUID.
    # Mock users without a real counterpart get user_uuid=None, which
    # disables the admin action buttons in the template.
    _MOCK_TO_REAL_USERNAME = {
        "USR-001": "admin",
        "USR-002": "demo",
        "USR-003": "test_verify",
        "USR-004": "verify_user",
    }
    real_username = _MOCK_TO_REAL_USERNAME.get(user_id)
    user_uuid = None
    if real_username:
        try:
            from apps.users.models import User
            real_user = User.objects.get(username=real_username)
            user_uuid = str(real_user.id)
        except Exception:
            pass
    profile["user_uuid"] = user_uuid

    context: dict = {"profile": profile, "role": user["role"]}

    # --- Driver-specific expanded report ---
    if user["role"] == "Driver":
        days = 30  # Generate 30 days so the 7D/14D/30D filter can slice
        today = datetime.now().date()

        # Daily commissions paid (day-by-day breakdown)
        commissions_daily = []
        performance_trend = []
        commission_trend = []
        cumulative_commission = 0.0

        for i in range(days):
            d = today - timedelta(days=days - 1 - i)
            date_str = d.strftime("%b %d")

            # Deterministic daily units sold (varies by seed)
            units = max(5, int(round(25 + 8 * math.sin(i / 2.5 + seed * 0.1) + i * 0.3)))
            # Commission per unit varies by driver (₱4–₱6 avg)
            rate_per_unit = 4.50 + (seed % 3) * 0.50
            daily_commission = round(units * rate_per_unit, 2)
            cumulative_commission = round(cumulative_commission + daily_commission, 2)

            commissions_daily.append({
                "date": date_str,
                "units": units,
                "rate": f"₱{rate_per_unit:.2f}",
                "amount": f"₱{daily_commission:,.2f}",
                "amount_raw": daily_commission,
            })
            performance_trend.append({
                "date": date_str,
                "units": units,
            })
            commission_trend.append({
                "date": date_str,
                "cumulative": cumulative_commission,
            })

        # Summary stats for the driver (computed over the full 30-day window;
        # the date-range filter on the client re-slices the trend charts and
        # MAC badges, while these top-level cards show the 30D aggregate).
        total_commissions = round(sum(c["amount_raw"] for c in commissions_daily), 2)
        total_units = sum(c["units"] for c in commissions_daily)
        avg_daily = round(total_commissions / days, 2)

        # Debts handled by this driver (credits they delivered that remain unpaid)
        debts_handled = [
            {
                "customer_name": "Aling Nena's Sari-Sari",
                "customer_id": "HY-8021",
                "amount": "₱1,850.00",
                "amount_raw": 1850.00,
                "date": "Aug 07, 2026",
                "status": "overdue",
                "status_label": "Overdue",
                "status_class": "bg-error/10 text-error",
                "row_border": "border-l-error",
                "days_overdue": 4,
            },
            {
                "customer_name": "Tita Linda's Eatery",
                "customer_id": "HY-5530",
                "amount": "₱640.00",
                "amount_raw": 640.00,
                "date": "Aug 05, 2026",
                "status": "pending",
                "status_label": "Pending",
                "status_class": "bg-[#D97706]/10 text-[#D97706]",
                "row_border": "border-l-[#D97706]",
                "days_overdue": 6,
            },
            {
                "customer_name": "Kuya Ramon Store",
                "customer_id": "HY-4421",
                "amount": "₱920.00",
                "amount_raw": 920.00,
                "date": "Jul 20, 2026",
                "status": "overdue",
                "status_label": "Overdue",
                "status_class": "bg-error/10 text-error",
                "row_border": "border-l-error",
                "days_overdue": 22,
            },
            {
                "customer_name": "Sunrise Canteen",
                "customer_id": "HY-3380",
                "amount": "₱420.00",
                "amount_raw": 420.00,
                "date": "Aug 08, 2026",
                "status": "paid",
                "status_label": "Paid",
                "status_class": "bg-tertiary/10 text-tertiary",
                "row_border": "border-l-tertiary",
                "days_overdue": 0,
            },
        ]
        debts_sum = round(sum(d["amount_raw"] for d in debts_handled), 2)
        debts_outstanding = round(
            sum(d["amount_raw"] for d in debts_handled if d["status"] != "paid"), 2
        )

        context.update({
            "is_driver": True,
            "driver_stats": [
                {
                    "key": "total_commissions",
                    "label": "Commissions Paid (30D)",
                    "value": f"₱{total_commissions:,.2f}",
                    "value_size": "2xl",
                    "subtitle": f"{total_units} units delivered",
                    "icon": "payments",
                    "accent": "tertiary",
                    "col_span": "md:col-span-4",
                },
                {
                    "key": "avg_daily",
                    "label": "Avg Daily Commission",
                    "value": f"₱{avg_daily:,.2f}",
                    "value_size": "2xl",
                    "subtitle": f"Over {days} days",
                    "icon": "trending_up",
                    "accent": "primary",
                    "col_span": "md:col-span-4",
                },
                {
                    "key": "debts_outstanding",
                    "label": "Outstanding Debts Handled",
                    "value": f"₱{debts_outstanding:,.2f}",
                    "value_size": "2xl",
                    "subtitle": f"{len(debts_handled)} customers, ₱{debts_sum:,.2f} total",
                    "icon": "dangerous",
                    "accent": "error",
                    "col_span": "md:col-span-4",
                },
            ],
            "commissions_daily": commissions_daily,
            "commissions_daily_json": json.dumps(commissions_daily).replace("'", "&#39;"),
            "performance_trend": performance_trend,
            "commission_trend": commission_trend,
            "performance_trend_json": json.dumps(performance_trend),
            "commission_trend_json": json.dumps(commission_trend),
            # Trends seed for the Alpine date-range filter + MAC badges.
            # The client slices this 30-day window to 7D/14D/30D/custom.
            "trends_seed": json.dumps({
                "labels": [p["date"] for p in performance_trend],
                "performance": [p["units"] for p in performance_trend],
                "commissions": [c["cumulative"] for c in commission_trend],
            }).replace("'", "&#39;"),
            "debts_handled": debts_handled,
            "debts_sum": f"₱{debts_sum:,.2f}",
            "debts_outstanding_amount": f"₱{debts_outstanding:,.2f}",
        })

    # --- Staff-specific expanded report ---
    elif user["role"] == "Staff":
        # Debts assigned to / named after this staff member
        debts_assigned = [
            {
                "customer_name": "Aling Nena's Sari-Sari",
                "customer_id": "HY-8021",
                "amount": "₱1,850.00",
                "amount_raw": 1850.00,
                "date": "Aug 07, 2026",
                "status": "overdue",
                "status_label": "Overdue",
                "status_class": "bg-error/10 text-error",
                "row_border": "border-l-error",
                "days_overdue": 4,
            },
            {
                "customer_name": "Metro Logistics",
                "customer_id": "HY-9011",
                "amount": "₱4,500.00",
                "amount_raw": 4500.00,
                "date": "Aug 10, 2026",
                "status": "pending",
                "status_label": "Pending",
                "status_class": "bg-[#D97706]/10 text-[#D97706]",
                "row_border": "border-l-[#D97706]",
                "days_overdue": 1,
            },
            {
                "customer_name": "Brgy. 7 Mini Mart",
                "customer_id": "HY-6644",
                "amount": "₱0.00",
                "amount_raw": 0.00,
                "date": "Jul 15, 2026",
                "status": "paid",
                "status_label": "Paid",
                "status_class": "bg-tertiary/10 text-tertiary",
                "row_border": "border-l-tertiary",
                "days_overdue": 0,
            },
        ]
        debts_sum = round(sum(d["amount_raw"] for d in debts_assigned), 2)
        debts_outstanding = round(
            sum(d["amount_raw"] for d in debts_assigned if d["status"] != "paid"), 2
        )

        context.update({
            "is_staff": True,
            "staff_stats": [
                {
                    "key": "debts_total",
                    "label": "Total Debts Assigned",
                    "value": f"₱{debts_sum:,.2f}",
                    "value_size": "2xl",
                    "subtitle": f"{len(debts_assigned)} customers",
                    "icon": "account_balance",
                    "accent": "primary",
                    "col_span": "md:col-span-6",
                },
                {
                    "key": "debts_outstanding",
                    "label": "Outstanding",
                    "value": f"₱{debts_outstanding:,.2f}",
                    "value_size": "2xl",
                    "subtitle": "Awaiting collection",
                    "icon": "dangerous",
                    "accent": "error",
                    "col_span": "md:col-span-6",
                },
            ],
            "debts_assigned": debts_assigned,
            "debts_sum": f"₱{debts_sum:,.2f}",
            "debts_outstanding_amount": f"₱{debts_outstanding:,.2f}",
        })

    # --- Admin: no performance or debt data ---
    else:
        context.update({
            "is_admin": True,
        })

    return context


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def employees_directory_view(request):
    """
    Renders the Employees & Users management page with two tabs:
      1. Directory          — overview stats + full users table
      2. Roles & Permissions — role cards with permission matrix

    Audit history is handled by the dedicated ``apps.audit`` page rather
    than a tab here.

    Currently uses mock data (``_mock_directory_data``,
    ``_mock_roles_data``) to prototype the layout for client approval.
    When backend services are ready, swap the mock calls for real
    selector functions that return the same context shape.
    """
    context = {}
    context.update(_mock_directory_data())
    context.update(_mock_roles_data())

    # Pre-compute accent classes for the directory stats row so the template
    # stays clean (mirrors the pattern used in apps.customers.views).
    for stat in context["stats"]:
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]

    return render(request, "employees/employees_directory.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def user_detail_view(request, user_id: str):
    """
    HTMX endpoint — returns the expanded report partial for a specific user.

    Renders role-specific content:
      - Driver:  daily commissions, performance/commission trends (mini
                 charts), debts handled + sum
      - Staff:   debts assigned + sum
      - Admin:   profile summary only

    The partial is designed to be swapped into ``#drawer-root`` by HTMX
    (a right-side slide-in drawer).  When real selectors replace the mock
    data function, the template will work unchanged.
    """
    context = _mock_user_detail_data(user_id)

    # Pre-compute accent classes for any stat rows (driver/staff)
    for stat in context.get("driver_stats", []):
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]
    for stat in context.get("staff_stats", []):
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]

    return render(request, "employees/partials/user_detail.html", context)
