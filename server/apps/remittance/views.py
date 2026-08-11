import json
import math
from datetime import date, datetime, timedelta

from django.contrib.auth.decorators import login_required
from django_ratelimit.decorators import ratelimit
from django.shortcuts import render


# ---------------------------------------------------------------------------
# Mock data — Add Remittance (create/finalize today's remittance workflow)
# Mirrors the Stitch "Add Remittance (Optimized)" screen.  Replace with real
# selectors/services once the backend is implemented.
# ---------------------------------------------------------------------------
def _mock_add_remittance_data() -> dict:
    # --- Master product catalogue (for the Add Product combobox) ---
    # `unit_price` is the selling price; `key` matches the keys in
    # `riders[*].commission_rates`.
    products = [
        {"key": "5gal_alk_round",    "name": "5 Gallon Alkaline (Round)", "unit_price": 40.00},
        {"key": "5gal_mineral_slim", "name": "5 Gallon Mineral (Slim)",   "unit_price": 35.00},
        {"key": "1gal_dispenser",    "name": "1 Gallon Dispenser",        "unit_price": 65.00},
        {"key": "350ml_case",        "name": "350ml Case (24 pcs)",       "unit_price": 120.00},
    ]

    # --- Riders, each with their own per-product commission rates and
    # --- their own product-line entries for today.
    # subtotal = (sold - credited) * unit_price   (credited deducts full price)
    # commission = (sold - credited) * commission_rate
    # Repayments (collected from the customer's page) restore sales and
    # commission: repayment amount is added to total sales, and the rider
    # earns commission on the repaid quantity.
    riders = [
        {
            "id": 1,
            "name": "Juan Dela Cruz",
            "vehicle": "TMX 125",
            "plate": "N-402",
            "selected": True,
            "commission_rates": {
                "5gal_alk_round": 5.00,
                "5gal_mineral_slim": 3.50,
                "1gal_dispenser": 8.00,
                "350ml_case": 12.00,
            },
            "commission_override": "",
            "product_lines": [
                {"product_key": "5gal_alk_round",    "sold": 42, "credited": 0, "borrowed": 3},
                {"product_key": "5gal_mineral_slim", "sold": 28, "credited": 5, "borrowed": 0},
            ],
            # Repayments collected from the customer's page within this
            # session.  Read-only on the remittance form — auto-populated
            # when a collection is recorded against this rider.
            "repayments": [
                {"payer": "Aling Nena Store", "product_key": "5gal_mineral_slim", "qty": 2, "amount": 70.00},
            ],
        },
        {
            "id": 2,
            "name": "Roberto Santos",
            "vehicle": "Smash 115",
            "plate": "W-991",
            "selected": False,
            "commission_rates": {
                "5gal_alk_round": 4.50,
                "5gal_mineral_slim": 3.00,
                "1gal_dispenser": 7.00,
                "350ml_case": 10.00,
            },
            "commission_override": "",
            "product_lines": [
                {"product_key": "5gal_alk_round", "sold": 35, "credited": 2, "borrowed": 1},
            ],
            "repayments": [
                {"payer": "Rizal Mini Mart", "product_key": "5gal_alk_round", "qty": 1, "amount": 40.00},
            ],
        },
        {
            "id": 3,
            "name": "Maria Garcia",
            "vehicle": "Mio i 125",
            "plate": "S-203",
            "selected": False,
            "commission_rates": {
                "5gal_alk_round": 5.50,
                "5gal_mineral_slim": 4.00,
                "1gal_dispenser": 8.50,
                "350ml_case": 13.00,
            },
            "commission_override": "",
            "product_lines": [
                {"product_key": "1gal_dispenser", "sold": 12, "credited": 0, "borrowed": 0},
                {"product_key": "350ml_case",     "sold": 8,  "credited": 1, "borrowed": 0},
            ],
            "repayments": [],
        },
    ]

    return {
        "today_date": datetime.now().strftime("%A, %b %d, %Y"),

        # --- Pinned summary KPIs (sticky top card) ---
        # NOTE: values are computed client-side by Alpine.js; these are initial
        # server-rendered values that match the seed data below.
        "summary": {
            "total_sales": "₱5,800.00",
            "net_remittance": "₱3,923.00",
            "tithes": "₱392.30",
            "total_expenses": "₱1,245.00",
            "total_commission": "₱632.00",
            "manual_offering": "₱0.00",
        },

        "riders": riders,
        "rider_position": "1 of 3",

        "products": products,

        # General expenses (decoupled from any rider)
        "expenses": [
            {"description": "Gasoline Refill (Petron)", "amount": "850.00"},
            {"description": "Seal Replacement (Round Caps)", "amount": "395.00"},
        ],

        # --- Spiritual obligations ---
        "tithe_rate": 0.10,
        "tithe_amount": "124.50",
        "offering_amount": "",
    }


# ---------------------------------------------------------------------------
# Mock data — Performance Trends (30-day time series for the history page)
# Deterministic pseudo-realistic series so the charts look the same on every
# render.  Replace with real aggregator selectors once the backend lands.
# ---------------------------------------------------------------------------
_TREND_RIDERS = [
    {"name": "Juan Dela Cruz",   "color": "#006591"},  # primary
    {"name": "Roberto Santos",   "color": "#505F76"},  # secondary
    {"name": "Maria Garcia",     "color": "#35AF80"},  # tertiary-container
    {"name": "Carlos Reyes",     "color": "#D97706"},  # warning amber
    {"name": "Ana Torres",       "color": "#7C3AED"},  # violet
    {"name": "Pedro Lim",        "color": "#0EA5E9"},  # sky
    {"name": "Liza Mendoza",     "color": "#E11D48"},  # rose
    {"name": "Ramon Cruz",       "color": "#059669"},  # emerald
    {"name": "Diana Villanueva", "color": "#4F46E5"},  # indigo
    {"name": "Mark Tan",         "color": "#EA580C"},  # orange
    {"name": "Sofia Ramos",      "color": "#0D9488"},  # teal
    {"name": "Erik Bautista",    "color": "#B45309"},  # dark amber
]


def _build_trend_series(days: int = 30) -> dict:
    """Build a deterministic 30-day trend dataset for the four history charts."""
    today = date.today()
    labels: list[str] = []
    total_sales: list[float] = []
    outstanding_debt: list[float] = []
    commissions_paid: list[float] = []

    # Per-rider units sold per day — each rider has a distinct rhythm.
    rider_units: list[list[int]] = [[] for _ in _TREND_RIDERS]

    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        labels.append(d.strftime("%b %d"))

        # Upward-trending weekly-seasonal sales curve.
        base = 4200 + (i * 35)
        weekly = 900 * math.sin((i / 7) * math.pi)
        noise = 220 * math.sin(i * 1.3)
        sales = max(1800.0, round(base + weekly + noise, 2))
        total_sales.append(sales)

        # Outstanding debt oscillates around a slowly declining baseline.
        debt_base = 18500 - (i * 60)
        debt_wave = 2600 * math.sin((i / 5) * math.pi + 1)
        debt = max(2000.0, round(debt_base + debt_wave, 2))
        outstanding_debt.append(debt)

        # Commissions track ~11% of sales with a one-day lag.
        lag_sales = total_sales[max(0, i - 1)]
        commissions_paid.append(round(lag_sales * 0.11, 2))

        # Rider units — each rider has a different base volume, cadence, and
        # growth slope, derived deterministically from their index.
        for idx in range(len(_TREND_RIDERS)):
            base_units = 28 - (idx * 1.8)
            cadence = 2.1 + (idx * 0.4)
            phase = idx * 0.7
            slope = 0.25 - (idx * 0.015)
            val = max(4, int(round(base_units + 10 * math.sin(i / cadence + phase) + i * slope)))
            rider_units[idx].append(val)

    rider_series = [
        {"name": r["name"], "color": r["color"], "units_sold": rider_units[idx]}
        for idx, r in enumerate(_TREND_RIDERS)
    ]

    return {
        "labels": labels,
        "total_sales": total_sales,
        "outstanding_debt": outstanding_debt,
        "commissions_paid": commissions_paid,
        "riders": rider_series,
    }


# ---------------------------------------------------------------------------
# Mock data — Remittance History (paginated list of past remittances)
# Mirrors the Stitch "Remittance History" screen.
# ---------------------------------------------------------------------------
def _mock_remittance_history_data() -> dict:
    trends = _build_trend_series(days=30)
    return {
        "today_date": datetime.now().strftime("%A, %b %d, %Y"),
        "trends": trends,
        # --- Bento summary cards ---
        "summary_cards": [
            {
                "label": "Total Remittance (MTD)",
                "value": "₱428,590.00",
                "accent_bar": "#10b981",
                "badge_text": "12%",
                "badge_icon": "trending_up",
                "badge_color": "#10b981",
            },
            {
                "label": "Unpaid Tithes",
                "value": "₱18,240.50",
                "accent_bar": "#f59e0b",
                "badge_text": "4 Items",
                "badge_icon": "warning",
                "badge_color": "text-error",
            },
            {
                "label": "AI Projected Profit (EOQ)",
                "value": "₱1,420,000.00",
                "accent_bar": "primary",
                "badge_text": "",
                "badge_icon": "auto_awesome",
                "badge_color": "text-primary",
                "shimmer": True,
            },
        ],

        # --- History table rows ---
        "remittances": [
            {
                "date": "2023-10-27",
                "created_by": "Juan Sebastian",
                "initials": "JS",
                "avatar_bg": "bg-secondary-container",
                "avatar_text": "text-on-secondary-container",
                "total_sales": "145,200.00",
                "net_profit": "32,400.00",
                "tithes": "3,240.00",
                "tithes_paid": False,
                "offering_paid": True,
                "unpaid": True,
            },
            {
                "date": "2023-10-26",
                "created_by": "Maria Luna",
                "initials": "ML",
                "avatar_bg": "bg-primary-container",
                "avatar_text": "text-on-primary-container",
                "total_sales": "89,450.00",
                "net_profit": "18,900.00",
                "tithes": "1,890.00",
                "tithes_paid": True,
                "offering_paid": True,
                "unpaid": False,
            },
            {
                "date": "2023-10-25",
                "created_by": "Ricardo Dalisay",
                "initials": "RD",
                "avatar_bg": "bg-surface-container-highest",
                "avatar_text": "text-on-surface",
                "total_sales": "210,000.00",
                "net_profit": "45,000.00",
                "tithes": "4,500.00",
                "tithes_paid": False,
                "offering_paid": False,
                "unpaid": True,
            },
            {
                "date": "2023-10-24",
                "created_by": "Juan Sebastian",
                "initials": "JS",
                "avatar_bg": "bg-secondary-container",
                "avatar_text": "text-on-secondary-container",
                "total_sales": "112,000.00",
                "net_profit": "22,100.00",
                "tithes": "2,210.00",
                "tithes_paid": True,
                "offering_paid": True,
                "unpaid": False,
            },
        ],

        # --- Pagination ---
        "pagination": {
            "showing": "Showing 4 of 24 records",
            "current_page": 1,
            "total_pages": 3,
        },

        # --- AI insight ---
        "ai_insight": (
            'Hydr8 detected a <span class="text-tertiary font-bold">7% increase</span> '
            "in tithe compliance compared to the previous month. The current cash flow "
            "allows for the scheduled maintenance of the San Pablo filtration facility "
            "without external financing."
        ),
    }


@login_required
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def add_remittance_view(request):
    """
    Renders the 'Add Remittance' workflow page.

    Currently uses mock data (``_mock_add_remittance_data``) to prototype the
    create/finalize daily remittance layout for client approval.  When backend
    services are ready, swap the mock call for real selector functions.
    """
    context = _mock_add_remittance_data()
    # Serialize the seed data so Alpine.js can hydrate the form client-side.
    # KPIs are recomputed live from this state on every input change.
    # The JSON is embedded inside a single-quoted x-data attribute, so we
    # escape any single quotes to avoid breaking the attribute boundary.
    context["alpine_seed"] = json.dumps({
        "riders": context["riders"],
        "products": context["products"],
        "expenses": context["expenses"],
        "titheRate": context["tithe_rate"],
        "manualOffering": context["offering_amount"],
        "selectedRiderId": next(
            (r["id"] for r in context["riders"] if r["selected"]),
            context["riders"][0]["id"],
        ),
    }).replace("'", "&#39;")
    return render(request, "remittance/add_remittance.html", context)


@login_required
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def remittance_history_view(request):
    """
    Renders the 'Remittance History' list page.

    Currently uses mock data (``_mock_remittance_history_data``) to prototype
    the paginated history table for client approval.
    """
    context = _mock_remittance_history_data()
    # Serialize the trend series so Alpine.js + ApexCharts can hydrate the
    # Performance Trends section and re-render on filter changes client-side.
    # The JSON is embedded inside a single-quoted x-data attribute, so we
    # escape any single quotes to avoid breaking the attribute boundary.
    context["trends_seed"] = json.dumps(context["trends"]).replace("'", "&#39;")
    return render(request, "remittance/remittance_history.html", context)
