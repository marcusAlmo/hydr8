from datetime import datetime

from django.shortcuts import render
from django.contrib.auth.decorators import login_required


def _mock_dashboard_data() -> dict:
    """
    Mock data for the dashboard prototype.

    This is a temporary fixture used to validate the dashboard layout and
    summary cards with the client before backend services are implemented.
    Once the real selectors/services are ready, replace this function with
    actual queries — the template already consumes these context keys.
    """
    return {
        # --- Top bar ---
        "today_date": datetime.now().strftime("%A, %b %d, %Y"),

        # --- Warning banner ---
        "warning_banner": {
            "show": True,
            "title": "No remittance for today yet",
            "message": "Operations are running but no financial data has been logged for this period.",
            "cta_text": "Create Today's Remittance",
        },

        # --- Summary cards (asymmetric 6/3/3 grid) ---
        "stats": [
            {
                "key": "today_sales",
                "label": "Today's Total Sales",
                "value": "₱12,458.50",
                "value_size": "4xl",
                "trend": "+14.2% from yesterday",
                "trend_direction": "up",
                "icon": "analytics",
                "accent": "primary",
                "col_span": "md:col-span-6",
            },
            {
                "key": "outstanding_debt",
                "label": "Outstanding Debt",
                "value": "₱28,940.12",
                "value_size": "2xl",
                "subtitle": "Total Unpaid Credits",
                "icon": "dangerous",
                "accent": "error",
                "col_span": "md:col-span-3",
            },
            {
                "key": "unreturned_containers",
                "label": "Unreturned Containers",
                "value": "47",
                "value_size": "2xl",
                "icon": "water_damage",
                "accent": "tertiary",
                "col_span": "md:col-span-3",
            },
        ],

        # --- Recent remittances table ---
        "recent_remittances": [
            {
                "date": "Oct 24, 2023",
                "total_sales": "₱14,200.00",
                "net_profit": "₱3,450.00",
                "tithes": "₱345.00",
                "tithes_status": "unpaid",
                "has_warning": True,
            },
            {
                "date": "Oct 23, 2023",
                "total_sales": "₱11,850.00",
                "net_profit": "₱2,900.00",
                "tithes": "₱290.00",
                "tithes_status": "paid",
                "has_warning": False,
            },
            {
                "date": "Oct 22, 2023",
                "total_sales": "₱15,100.00",
                "net_profit": "₱4,100.00",
                "tithes": "₱410.00",
                "tithes_status": "unpaid",
                "has_warning": True,
            },
            {
                "date": "Oct 21, 2023",
                "total_sales": "₱9,900.00",
                "net_profit": "₱1,800.00",
                "tithes": "₱180.00",
                "tithes_status": "paid",
                "has_warning": False,
            },
        ],

        # --- Long-running debts (unpaid rider-issued credits) ---
        "long_running_debts": [
            {
                "customer": "Aling Nena's Sari-Sari",
                "rider": "Rider Dela Cruz",
                "amount": "₱1,850.00",
                "age_days": 62,
                "issued_on": "Jun 11, 2023",
                "severity": "critical",
            },
            {
                "customer": "Kuya Ramon Store",
                "rider": "Rider Santos",
                "amount": "₱920.00",
                "age_days": 48,
                "issued_on": "Jun 25, 2023",
                "severity": "critical",
            },
            {
                "customer": "Brgy. 7 Mini Mart",
                "rider": "Rider Dela Cruz",
                "amount": "₱1,200.00",
                "age_days": 35,
                "issued_on": "Jul 08, 2023",
                "severity": "warning",
            },
            {
                "customer": "Tita Linda's Eatery",
                "rider": "Rider Bautista",
                "amount": "₱640.00",
                "age_days": 31,
                "issued_on": "Jul 12, 2023",
                "severity": "warning",
            },
        ],

        # --- AI Insights panel ---
        "ai_insights": [
            {
                "tags": [
                    {"label": "Rider Performance", "variant": "primary"},
                    {"label": "Efficiency", "variant": "primary"},
                ],
                "html": (
                    "<strong class=\"font-bold\">Rider Dela Cruz</strong> contributed "
                    "<span class=\"text-primary font-bold\">38%</span> of today's gross revenue. "
                    "His route optimization has decreased fuel cost by 12%."
                ),
                "variant": "primary",
            },
            {
                "tags": [
                    {"label": "Inventory Alert", "variant": "error"},
                ],
                "html": (
                    "Alkaline 5L stock is <span class=\"text-error font-bold\">Critically Low</span>. "
                    "Based on velocity, you will stock out by 2 PM tomorrow."
                ),
                "variant": "error",
            },
            {
                "tags": [
                    {"label": "Trend Analysis", "variant": "neutral"},
                ],
                "html": (
                    "Credit defaults have risen by <span class=\"text-error font-bold\">5%</span> this week. "
                    "Suggest tightening credit terms for new customers."
                ),
                "variant": "primary",
            },
        ],
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

# Tag variant → Tailwind classes for AI insight tag chips.
_TAG_VARIANT_CLASSES = {
    "primary": "bg-surface-container-high text-primary border border-primary/10",
    "error": "bg-error/10 text-error border border-error/10",
    "neutral": "bg-surface-container-high text-on-secondary-fixed-variant border border-outline-variant/30",
}

# AI insight card variant → container classes.
_INSIGHT_VARIANT_CLASSES = {
    "primary": "bg-primary-container/5 border border-primary-container/10 hover:bg-primary-container/10",
    "error": "bg-error/5 border border-error/10 hover:bg-error/10",
}


@login_required
def dashboard_view(request):
    """
    Renders the main analytics dashboard.

    Currently uses mock data (``_mock_dashboard_data``) to prototype the
    layout and summary cards for client approval.  When backend services
    are ready, swap the mock call for real selector functions that return
    the same context shape.
    """
    context = _mock_dashboard_data()

    # Pre-compute accent classes so the template stays clean.
    for stat in context["stats"]:
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]

    # Pre-compute tag and card classes for AI insights.
    for insight in context["ai_insights"]:
        insight["card_class"] = _INSIGHT_VARIANT_CLASSES.get(
            insight["variant"], _INSIGHT_VARIANT_CLASSES["primary"]
        )
        for tag in insight["tags"]:
            tag["class"] = _TAG_VARIANT_CLASSES.get(
                tag["variant"], _TAG_VARIANT_CLASSES["neutral"]
            )

    return render(request, "analytics/dashboard.html", context)
