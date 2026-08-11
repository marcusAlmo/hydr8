from datetime import datetime, timedelta

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit


def _mock_customers_data() -> dict:
    """
    Mock data for the Customers list prototype.

    Temporary fixture used to validate the Customers layout and summary
    cards with the client before backend services are implemented. Once
    real selectors/services are ready, replace this function with actual
    queries — the template already consumes these context keys.

    Field shape mirrors the Customer model:
      name, address, contact_number, debt_balance,
      borrowed_round_8gal, borrowed_slim_8gal, borrowed_other,
      last_credit_at, notes
    """
    now = datetime.now()

    return {
        # --- Top bar ---
        "today_date": now.strftime("%A, %b %d, %Y"),

        # --- Summary cards (asymmetric grid) ---
        "stats": [
            {
                "key": "total_customers",
                "label": "Total Customers",
                "value": "1,248",
                "value_size": "4xl",
                "trend": "+12 this month",
                "trend_direction": "up",
                "icon": "group",
                "accent": "primary",
                "col_span": "md:col-span-4",
            },
            {
                "key": "total_debt",
                "label": "Total Outstanding Debt",
                "value": "₱28,940.12",
                "value_size": "3xl",
                "subtitle": "48 active debtors",
                "icon": "dangerous",
                "accent": "error",
                "col_span": "md:col-span-4",
            },
            {
                "key": "pending_containers",
                "label": "Unreturned Containers",
                "value": "382",
                "value_size": "4xl",
                "subtitle": "Across 112 customers",
                "icon": "water_damage",
                "accent": "warning",
                "col_span": "md:col-span-4",
            },
        ],

        # --- Filter chips ---
        "filters": [
            {"label": "All", "count": 1248, "active": True},
            {"label": "Has Debt", "count": 48, "active": False},
            {"label": "Has Borrowed Items", "count": 112, "active": False},
            {"label": "Clear Accounts", "count": 1088, "active": False},
        ],

        # --- Customer table ---
        "customers": [
            {
                "id": "HY-8021",
                "name": "Aling Nena's Sari-Sari",
                "initials": "AN",
                "address": "Brgy. 14, Mabini St., Calamba, Laguna",
                "contact_number": "0917-845-2103",
                "debt_balance": "₱1,850.00",
                "debt_class": "text-error",
                "borrowed_round_8gal": 8,
                "borrowed_slim_8gal": 4,
                "borrowed_other": 0,
                "borrowed_total": 12,
                "borrowed_class": "text-on-surface-variant",
                "payable_amount": "₱1,200.00",
                "last_credit_at": "4 days ago",
                "row_border": "border-l-[#D97706]",
                "has_debt": True,
            },
            {
                "id": "HY-7712",
                "name": "Aqua Services Inc.",
                "initials": "AS",
                "address": "Phase 1, Laguna Technopark, Santa Rosa, Laguna",
                "contact_number": "0998-123-4567",
                "debt_balance": "₱0.00",
                "debt_class": "text-tertiary",
                "borrowed_round_8gal": 0,
                "borrowed_slim_8gal": 0,
                "borrowed_other": 0,
                "borrowed_total": 0,
                "borrowed_class": "text-on-surface-variant",
                "payable_amount": "₱0.00",
                "last_credit_at": "12 days ago",
                "row_border": "border-l-transparent",
                "has_debt": False,
            },
            {
                "id": "HY-9011",
                "name": "Metro Logistics",
                "initials": "ML",
                "address": "Unit 2C, SM City, Bacoor, Cavite",
                "contact_number": "0922-555-0192",
                "debt_balance": "₱0.00",
                "debt_class": "text-tertiary",
                "borrowed_round_8gal": 30,
                "borrowed_slim_8gal": 12,
                "borrowed_other": 3,
                "borrowed_total": 45,
                "borrowed_class": "text-error",
                "payable_amount": "₱4,500.00",
                "last_credit_at": "1 day ago",
                "row_border": "border-l-[#D97706]",
                "has_debt": False,
            },
            {
                "id": "HY-4421",
                "name": "Kuya Ramon Store",
                "initials": "KR",
                "address": "Brgy. 7, Rizal Ave., Tanauan, Batangas",
                "contact_number": "0915-330-7788",
                "debt_balance": "₱920.00",
                "debt_class": "text-error",
                "borrowed_round_8gal": 1,
                "borrowed_slim_8gal": 1,
                "borrowed_other": 0,
                "borrowed_total": 2,
                "borrowed_class": "text-on-surface-variant",
                "payable_amount": "₱20.00",
                "last_credit_at": "22 days ago",
                "row_border": "border-l-error",
                "has_debt": True,
            },
            {
                "id": "HY-5530",
                "name": "Tita Linda's Eatery",
                "initials": "TL",
                "address": "Purok 3, Maharlika Hwy, Lipa City, Batangas",
                "contact_number": "0906-412-8890",
                "debt_balance": "₱640.00",
                "debt_class": "text-error",
                "borrowed_round_8gal": 6,
                "borrowed_slim_8gal": 3,
                "borrowed_other": 0,
                "borrowed_total": 9,
                "borrowed_class": "text-on-surface-variant",
                "payable_amount": "₱540.00",
                "last_credit_at": "6 days ago",
                "row_border": "border-l-[#D97706]",
                "has_debt": True,
            },
            {
                "id": "HY-6644",
                "name": "Brgy. 7 Mini Mart",
                "initials": "BM",
                "address": "Brgy. 7 Hall, Poblacion, Lipa City, Batangas",
                "contact_number": "0917-220-1145",
                "debt_balance": "₱0.00",
                "debt_class": "text-tertiary",
                "borrowed_round_8gal": 0,
                "borrowed_slim_8gal": 0,
                "borrowed_other": 0,
                "borrowed_total": 0,
                "borrowed_class": "text-on-surface-variant",
                "payable_amount": "₱0.00",
                "last_credit_at": "30 days ago",
                "row_border": "border-l-transparent",
                "has_debt": False,
            },
        ],

        # --- Pagination ---
        "pagination": {
            "showing_from": 1,
            "showing_to": 6,
            "total": 1248,
            "total_display": "1,248",
            "current_page": 1,
            "total_pages": 208,
        },
    }


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


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def customer_list_view(request):
    """
    Renders the Customers list page.

    Currently uses mock data (``_mock_customers_data``) to prototype the
    layout and summary cards for client approval. When backend services
    are ready, swap the mock call for real selector functions that return
    the same context shape.
    """
    context = _mock_customers_data()

    # Pre-compute accent classes so the template stays clean.
    for stat in context["stats"]:
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]

    return render(request, "customers/customer_list.html", context)
