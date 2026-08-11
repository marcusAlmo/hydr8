from datetime import datetime, timedelta

from django.http import HttpResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
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


def _mock_customers_data() -> dict:
    """
    Mock data for the Customers list prototype (Summary tab).

    Temporary fixture used to validate the Customers layout, summary cards,
    and anomaly indicators with the client before backend services are
    implemented. Once real selectors/services are ready, replace this
    function with actual queries — the template already consumes these
    context keys.

    Field shape mirrors the Customer model:
      name, address, contact_number, debt_balance, status,
      borrowed_round_8gal, borrowed_slim_8gal, borrowed_other,
      last_credit_at

    Address and contact_number are optional (may be empty strings).
    Each row also carries numeric ``*_raw`` / ``last_credit_days`` keys
    used by the sortable table endpoint for server-side ordering.
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

        # --- Filter chips (Clear Accounts removed; Anomalous added) ---
        "filters": [
            {"label": "All", "count": 1248, "active": True},
            {"label": "Has Debt", "count": 48, "active": False},
            {"label": "Has Borrowed Items", "count": 112, "active": False},
            {"label": "Anomalous", "count": 7, "active": False},
        ],

        # --- Customer table ---
        # status: 'active' | 'flagged' | 'blacklisted'
        # anomaly_badge: rendered chip when status != active
        "customers": [
            {
                "id": "HY-8021",
                "name": "Aling Nena's Sari-Sari",
                "initials": "AN",
                "address": "Brgy. 14, Mabini St., Calamba, Laguna",
                "contact_number": "0917-845-2103",
                "debt_balance": "₱1,850.00",
                "debt_balance_raw": 1850.00,
                "debt_class": "text-error",
                "borrowed_round_8gal": 8,
                "borrowed_slim_8gal": 4,
                "borrowed_other": 0,
                "borrowed_total": 12,
                "borrowed_class": "text-on-surface-variant",
                "payable_amount": "₱1,200.00",
                "payable_amount_raw": 1200.00,
                "last_credit_at": "4 days ago",
                "last_credit_days": 4,
                "row_border": "border-l-[#D97706]",
                "has_debt": True,
                "status": "flagged",
                "anomaly_badge": "FLAGGED",
                "anomaly_reason": "3 overdue cycles in 60 days",
            },
            {
                "id": "HY-7712",
                "name": "Aqua Services Inc.",
                "initials": "AS",
                "address": "Phase 1, Laguna Technopark, Santa Rosa, Laguna",
                "contact_number": "0998-123-4567",
                "debt_balance": "₱0.00",
                "debt_balance_raw": 0.00,
                "debt_class": "text-tertiary",
                "borrowed_round_8gal": 0,
                "borrowed_slim_8gal": 0,
                "borrowed_other": 0,
                "borrowed_total": 0,
                "borrowed_class": "text-on-surface-variant",
                "payable_amount": "₱0.00",
                "payable_amount_raw": 0.00,
                "last_credit_at": "12 days ago",
                "last_credit_days": 12,
                "row_border": "border-l-transparent",
                "has_debt": False,
                "status": "active",
                "anomaly_badge": "",
                "anomaly_reason": "",
            },
            {
                "id": "HY-9011",
                "name": "Metro Logistics",
                "initials": "ML",
                "address": "Unit 2C, SM City, Bacoor, Cavite",
                "contact_number": "0922-555-0192",
                "debt_balance": "₱0.00",
                "debt_balance_raw": 0.00,
                "debt_class": "text-tertiary",
                "borrowed_round_8gal": 30,
                "borrowed_slim_8gal": 12,
                "borrowed_other": 3,
                "borrowed_total": 45,
                "borrowed_class": "text-error",
                "payable_amount": "₱4,500.00",
                "payable_amount_raw": 4500.00,
                "last_credit_at": "1 day ago",
                "last_credit_days": 1,
                "row_border": "border-l-[#D97706]",
                "has_debt": False,
                "status": "flagged",
                "anomaly_badge": "FLAGGED",
                "anomaly_reason": "45 unreturned containers (3× branch avg)",
            },
            {
                "id": "HY-4421",
                "name": "Kuya Ramon Store",
                "initials": "KR",
                "address": "Brgy. 7, Rizal Ave., Tanauan, Batangas",
                "contact_number": "0915-330-7788",
                "debt_balance": "₱920.00",
                "debt_balance_raw": 920.00,
                "debt_class": "text-error",
                "borrowed_round_8gal": 1,
                "borrowed_slim_8gal": 1,
                "borrowed_other": 0,
                "borrowed_total": 2,
                "borrowed_class": "text-on-surface-variant",
                "payable_amount": "₱20.00",
                "payable_amount_raw": 20.00,
                "last_credit_at": "22 days ago",
                "last_credit_days": 22,
                "row_border": "border-l-error",
                "has_debt": True,
                "status": "blacklisted",
                "anomaly_badge": "BLACKLISTED",
                "anomaly_reason": "5 failed collections; debt unpaid 90+ days",
            },
            {
                "id": "HY-5530",
                "name": "Tita Linda's Eatery",
                "initials": "TL",
                "address": "Purok 3, Maharlika Hwy, Lipa City, Batangas",
                "contact_number": "0906-412-8890",
                "debt_balance": "₱640.00",
                "debt_balance_raw": 640.00,
                "debt_class": "text-error",
                "borrowed_round_8gal": 6,
                "borrowed_slim_8gal": 3,
                "borrowed_other": 0,
                "borrowed_total": 9,
                "borrowed_class": "text-on-surface-variant",
                "payable_amount": "₱540.00",
                "payable_amount_raw": 540.00,
                "last_credit_at": "6 days ago",
                "last_credit_days": 6,
                "row_border": "border-l-[#D97706]",
                "has_debt": True,
                "status": "active",
                "anomaly_badge": "",
                "anomaly_reason": "",
            },
            {
                "id": "HY-6644",
                "name": "Brgy. 7 Mini Mart",
                "initials": "BM",
                "address": "",
                "contact_number": "",
                "debt_balance": "₱0.00",
                "debt_balance_raw": 0.00,
                "debt_class": "text-tertiary",
                "borrowed_round_8gal": 0,
                "borrowed_slim_8gal": 0,
                "borrowed_other": 0,
                "borrowed_total": 0,
                "borrowed_class": "text-on-surface-variant",
                "payable_amount": "₱0.00",
                "payable_amount_raw": 0.00,
                "last_credit_at": "30 days ago",
                "last_credit_days": 30,
                "row_border": "border-l-transparent",
                "has_debt": False,
                "status": "active",
                "anomaly_badge": "",
                "anomaly_reason": "",
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


def _mock_debt_management_data() -> dict:
    """
    Mock data for the Debt Management tab.

    Lists customers with outstanding debt, sorted by debt balance descending.
    Each row exposes collection-relevant metadata: days overdue, last payment
    date, suggested action. Replaces the summary-table view with a focused
    collections workflow.
    """
    return {
        "debt_stats": [
            {
                "key": "total_debt",
                "label": "Total Outstanding",
                "value": "₱28,940.12",
                "value_size": "3xl",
                "subtitle": "Across 48 debtors",
                "icon": "dangerous",
                "accent": "error",
                "col_span": "md:col-span-6",
            },
            {
                "key": "overdue_30",
                "label": "Overdue 30+ Days",
                "value": "14",
                "value_size": "4xl",
                "subtitle": "₱11,220.00 at risk",
                "icon": "schedule",
                "accent": "warning",
                "col_span": "md:col-span-3",
            },
            {
                "key": "avg_days_overdue",
                "label": "Avg Days Overdue",
                "value": "18",
                "value_size": "4xl",
                "subtitle": "Across active debtors",
                "icon": "hourglass_top",
                "accent": "warning",
                "col_span": "md:col-span-3",
            },
        ],
        "debt_rows": [
            {
                "id": "HY-4421",
                "name": "Kuya Ramon Store",
                "initials": "KR",
                "debt_balance": "₱4,500.00",
                "days_overdue": 64,
                "days_overdue_class": "text-error",
                "last_payment_at": "Never",
                "last_payment_class": "text-error",
                "suggested_action": "Send final demand",
                "action_class": "bg-error text-on-primary",
                "status": "blacklisted",
                "anomaly_badge": "BLACKLISTED",
            },
            {
                "id": "HY-8021",
                "name": "Aling Nena's Sari-Sari",
                "initials": "AN",
                "debt_balance": "₱1,850.00",
                "days_overdue": 12,
                "days_overdue_class": "text-[#D97706]",
                "last_payment_at": "8 days ago",
                "last_payment_class": "text-on-surface-variant",
                "suggested_action": "Call to collect",
                "action_class": "bg-primary text-on-primary",
                "status": "flagged",
                "anomaly_badge": "FLAGGED",
            },
            {
                "id": "HY-5530",
                "name": "Tita Linda's Eatery",
                "initials": "TL",
                "debt_balance": "₱640.00",
                "days_overdue": 6,
                "days_overdue_class": "text-[#D97706]",
                "last_payment_at": "5 days ago",
                "last_payment_class": "text-on-surface-variant",
                "suggested_action": "Call to collect",
                "action_class": "bg-primary text-on-primary",
                "status": "active",
                "anomaly_badge": "",
            },
            {
                "id": "HY-3380",
                "name": "Sunrise Canteen",
                "initials": "SC",
                "debt_balance": "₱420.00",
                "days_overdue": 3,
                "days_overdue_class": "text-on-surface-variant",
                "last_payment_at": "2 days ago",
                "last_payment_class": "text-on-surface-variant",
                "suggested_action": "Monitor",
                "action_class": "bg-surface-container text-on-surface-variant",
                "status": "active",
                "anomaly_badge": "",
            },
        ],
        "debt_pagination": {
            "showing_from": 1,
            "showing_to": 4,
            "total": 48,
            "total_display": "48",
            "current_page": 1,
            "total_pages": 12,
        },
    }


def _mock_ranking_data() -> dict:
    """
    Mock data for the Ranking tab.

    Two leaderboards:
      1. Top Payers — ranked by payment reliability (on-time ratio, avg
         payment turnaround, payment frequency).
      2. Prompt Returners — ranked by container return speed and volume.

    Both surfaces exist to *reward* good behaviour (loyalty perks,
    priority delivery, credit limit increases).
    """
    return {
        "ranking_stats": [
            {
                "key": "top_payers",
                "label": "Reliable Payers",
                "value": "186",
                "value_size": "4xl",
                "subtitle": "≥90% on-time ratio",
                "icon": "verified",
                "accent": "tertiary",
                "col_span": "md:col-span-6",
            },
            {
                "key": "prompt_returners",
                "label": "Prompt Returners",
                "value": "94",
                "value_size": "4xl",
                "subtitle": "Avg return ≤ 2 days",
                "icon": "cached",
                "accent": "tertiary",
                "col_span": "md:col-span-3",
            },
            {
                "key": "avg_pay_time",
                "label": "Avg Pay Turnaround",
                "value": "3.2d",
                "value_size": "4xl",
                "subtitle": "Across all debtors",
                "icon": "timer",
                "accent": "primary",
                "col_span": "md:col-span-3",
            },
        ],
        # --- Top Payers leaderboard ---
        "top_payers": [
            {
                "rank": 1,
                "rank_class": "bg-tertiary text-on-primary",
                "id": "HY-7712",
                "name": "Aqua Services Inc.",
                "initials": "AS",
                "on_time_ratio": "100%",
                "avg_payment_days": "1.0",
                "payment_count": 42,
                "total_paid": "₱86,400.00",
                "tier": "Gold",
                "tier_class": "bg-tertiary-container/30 text-tertiary",
            },
            {
                "rank": 2,
                "rank_class": "bg-tertiary-container text-tertiary",
                "id": "HY-6644",
                "name": "Brgy. 7 Mini Mart",
                "initials": "BM",
                "on_time_ratio": "98%",
                "avg_payment_days": "1.4",
                "payment_count": 31,
                "total_paid": "₱52,200.00",
                "tier": "Gold",
                "tier_class": "bg-tertiary-container/30 text-tertiary",
            },
            {
                "rank": 3,
                "rank_class": "bg-surface-container-high text-on-surface-variant",
                "id": "HY-1190",
                "name": "Lipa Public Market Stall 14",
                "initials": "LM",
                "on_time_ratio": "96%",
                "avg_payment_days": "1.8",
                "payment_count": 27,
                "total_paid": "₱41,080.00",
                "tier": "Silver",
                "tier_class": "bg-surface-container-high text-on-surface-variant",
            },
            {
                "rank": 4,
                "rank_class": "bg-surface-container-high text-on-surface-variant",
                "id": "HY-2208",
                "name": "Rizal Coffee House",
                "initials": "RC",
                "on_time_ratio": "94%",
                "avg_payment_days": "2.1",
                "payment_count": 22,
                "total_paid": "₱33,540.00",
                "tier": "Silver",
                "tier_class": "bg-surface-container-high text-on-surface-variant",
            },
            {
                "rank": 5,
                "rank_class": "bg-surface-container-high text-on-surface-variant",
                "id": "HY-5530",
                "name": "Tita Linda's Eatery",
                "initials": "TL",
                "on_time_ratio": "91%",
                "avg_payment_days": "2.6",
                "payment_count": 18,
                "total_paid": "₱24,800.00",
                "tier": "Bronze",
                "tier_class": "bg-surface-container text-on-surface-variant",
            },
        ],
        # --- Prompt Returners leaderboard ---
        "prompt_returners": [
            {
                "rank": 1,
                "rank_class": "bg-tertiary text-on-primary",
                "id": "HY-7712",
                "name": "Aqua Services Inc.",
                "initials": "AS",
                "avg_return_days": "0.5",
                "return_count": 120,
                "containers_returned": 480,
                "on_time_ratio": "100%",
            },
            {
                "rank": 2,
                "rank_class": "bg-tertiary-container text-tertiary",
                "id": "HY-1190",
                "name": "Lipa Public Market Stall 14",
                "initials": "LM",
                "avg_return_days": "1.1",
                "return_count": 88,
                "containers_returned": 312,
                "on_time_ratio": "97%",
            },
            {
                "rank": 3,
                "rank_class": "bg-surface-container-high text-on-surface-variant",
                "id": "HY-6644",
                "name": "Brgy. 7 Mini Mart",
                "initials": "BM",
                "avg_return_days": "1.4",
                "return_count": 64,
                "containers_returned": 220,
                "on_time_ratio": "95%",
            },
            {
                "rank": 4,
                "rank_class": "bg-surface-container-high text-on-surface-variant",
                "id": "HY-2208",
                "name": "Rizal Coffee House",
                "initials": "RC",
                "avg_return_days": "1.7",
                "return_count": 51,
                "containers_returned": 168,
                "on_time_ratio": "92%",
            },
            {
                "rank": 5,
                "rank_class": "bg-surface-container-high text-on-surface-variant",
                "id": "HY-5530",
                "name": "Tita Linda's Eatery",
                "initials": "TL",
                "avg_return_days": "2.0",
                "return_count": 39,
                "containers_returned": 124,
                "on_time_ratio": "90%",
            },
        ],
    }


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def customer_list_view(request):
    """
    Renders the Customers page with three tabs:
      1. Summary       — overview stats + full customer table
      2. Debt Management — focused collections workflow
      3. Ranking       — top payers + prompt container returners

    Currently uses mock data (``_mock_customers_data``,
    ``_mock_debt_management_data``, ``_mock_ranking_data``) to prototype
    the layout for client approval. When backend services are ready, swap
    the mock calls for real selector functions that return the same
    context shape. Tab switching is handled client-side by Alpine.js
    (no HTMX round-trip needed for the prototype).
    """
    context = _mock_customers_data()
    context.update(_mock_debt_management_data())
    context.update(_mock_ranking_data())

    # Pre-compute accent classes so the template stays clean.
    for stat in context["stats"]:
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]
    for stat in context["debt_stats"]:
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]
    for stat in context["ranking_stats"]:
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]

    # Default sort state for the customer table headers (name, asc).
    context["sort_state"] = {"field": _DEFAULT_SORT, "direction": _DEFAULT_DIR, "next_dir": "desc"}

    return render(request, "customers/customer_list.html", context)


# ---------------------------------------------------------------------------
# Customer detail (HTMX modal)
# ---------------------------------------------------------------------------
# Detail-only enrichment fields keyed by customer ID. These are prototype
# values that don't belong in the list mock (they'd bloat the table payload).
# When real selectors land, replace this dict with a
# ``get_customer_detail(customer_id)`` selector returning the same shape.
_DETAIL_ENRICHMENT: dict[str, dict] = {
    "HY-8021": {
        "member_since": "Jan 2023",
        "total_credits": 38,
        "credit_limit": "₱3,000.00",
        "last_payment_at": "8 days ago",
    },
    "HY-7712": {
        "member_since": "Mar 2022",
        "total_credits": 142,
        "credit_limit": "₱10,000.00",
        "last_payment_at": "12 days ago",
    },
    "HY-9011": {
        "member_since": "Sep 2023",
        "total_credits": 67,
        "credit_limit": "₱8,000.00",
        "last_payment_at": "1 day ago",
    },
    "HY-4421": {
        "member_since": "Feb 2021",
        "total_credits": 91,
        "credit_limit": "₱1,500.00",
        "last_payment_at": "Never",
    },
    "HY-5530": {
        "member_since": "Nov 2022",
        "total_credits": 54,
        "credit_limit": "₱2,500.00",
        "last_payment_at": "5 days ago",
    },
    "HY-6644": {
        "member_since": "Jul 2023",
        "total_credits": 31,
        "credit_limit": "₱2,000.00",
        "last_payment_at": "30 days ago",
    },
}


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def customer_detail_view(request, customer_id: str):
    """
    HTMX endpoint — returns the detail modal partial for a single
    customer, showing full profile, financial summary, borrowed
    container breakdown, and anomaly context.

    The customer table row triggers an HTMX GET that swaps this modal
    partial into ``#modal-root`` (mirrors the audit log detail pattern).
    Uses ``str`` path converter because customer IDs are formatted
    ``HY-XXXX`` (not integers).
    """
    customers = _mock_customers_data()["customers"]
    customer = next((c for c in customers if c["id"] == customer_id), None)

    if customer is None:
        return HttpResponse("Customer not found.", status=404)

    # Merge detail-only enrichment fields (falls back to neutral defaults
    # so the modal still renders if a new mock customer is added without
    # an enrichment entry).
    enrichment = _DETAIL_ENRICHMENT.get(customer_id, {})
    customer["member_since"] = enrichment.get("member_since", "—")
    customer["total_credits"] = enrichment.get("total_credits", 0)
    customer["credit_limit"] = enrichment.get("credit_limit", "₱0.00")
    customer["last_payment_at"] = enrichment.get("last_payment_at", "—")

    # Status badge styling for the modal header.
    _STATUS_BADGE_CLASSES = {
        "active": "bg-tertiary-container/30 text-tertiary border-tertiary/30",
        "flagged": "bg-[#D97706]/15 text-[#D97706] border-[#D97706]/30",
        "blacklisted": "bg-error/10 text-error border-error/30",
    }
    _STATUS_LABELS = {
        "active": "Active",
        "flagged": "Flagged",
        "blacklisted": "Blacklisted",
    }
    customer["status_badge_class"] = _STATUS_BADGE_CLASSES.get(
        customer["status"], _STATUS_BADGE_CLASSES["active"]
    )
    customer["status_label"] = _STATUS_LABELS.get(
        customer["status"], customer["status"].title()
    )

    # A customer can only be deleted when there are no pending borrowed
    # containers and no outstanding debt. Re-checked server-side in the
    # delete view to guard against stale modal state.
    customer["can_delete"] = (
        customer.get("borrowed_total", 0) == 0 and not customer.get("has_debt", False)
    )

    return render(
        request,
        "customers/partials/detail_modal.html",
        {"customer": customer},
    )


# ---------------------------------------------------------------------------
# Customer collect (HTMX modal)
# ---------------------------------------------------------------------------
# Mock collect data keyed by customer ID. Each entry lists the open
# credit lines (accredited items) AND borrowed container entries, each
# tagged with the rider who handled the transaction. This lets the
# operator record collections per-rider so the correct rider receives
# commission credit for the payment.
#
# Rider shape: { id, name, initials, driver_code }
# Credit line shape: { id, product, qty_credited, qty_remaining,
#                      unit_price, total_credit, rider }
# Borrowed entry shape: { id, container_key, container_label, outstanding, rider }
#
# When real selectors land, replace this with
# ``get_collect_context(customer_id)`` returning the same shape.
_MOCK_RIDERS: dict[str, dict] = {
    "R-001": {"id": "R-001", "name": "Juan Dela Cruz",   "initials": "JC", "driver_code": "DRV-001"},
    "R-004": {"id": "R-004", "name": "Roberto Santos",   "initials": "RS", "driver_code": "DRV-004"},
    "R-012": {"id": "R-012", "name": "Maria Garcia",     "initials": "MG", "driver_code": "DRV-012"},
}

_COLLECT_ENRICHMENT: dict[str, dict] = {
    "HY-8021": {
        # 8 round + 4 slim, split across two riders
        "credit_lines": [
            {
                "id": "CL-8021-01",
                "product": "Round 8gal — Refill",
                "qty_credited": 5,
                "qty_remaining": 5,
                "unit_price": "₱150.00",
                "total_credit": "₱750.00",
                "rider": _MOCK_RIDERS["R-001"],
            },
            {
                "id": "CL-8021-02",
                "product": "Round 8gal — Refill",
                "qty_credited": 3,
                "qty_remaining": 3,
                "unit_price": "₱150.00",
                "total_credit": "₱450.00",
                "rider": _MOCK_RIDERS["R-004"],
            },
            {
                "id": "CL-8021-03",
                "product": "Slim 8gal — Refill",
                "qty_credited": 4,
                "qty_remaining": 4,
                "unit_price": "₱162.50",
                "total_credit": "₱650.00",
                "rider": _MOCK_RIDERS["R-001"],
            },
        ],
        "borrowed_entries": [
            {"id": "B-8021-01", "container_key": "round_8gal", "container_label": "Round 8gal", "outstanding": 5, "rider": _MOCK_RIDERS["R-001"]},
            {"id": "B-8021-02", "container_key": "round_8gal", "container_label": "Round 8gal", "outstanding": 3, "rider": _MOCK_RIDERS["R-004"]},
            {"id": "B-8021-03", "container_key": "slim_8gal",  "container_label": "Slim 8gal",  "outstanding": 4, "rider": _MOCK_RIDERS["R-001"]},
        ],
    },
    "HY-4421": {
        "credit_lines": [
            {
                "id": "CL-4421-01",
                "product": "Round 8gal — Refill",
                "qty_credited": 1,
                "qty_remaining": 1,
                "unit_price": "₱150.00",
                "total_credit": "₱150.00",
                "rider": _MOCK_RIDERS["R-012"],
            },
            {
                "id": "CL-4421-02",
                "product": "Slim 8gal — Refill",
                "qty_credited": 1,
                "qty_remaining": 1,
                "unit_price": "₱170.00",
                "total_credit": "₱170.00",
                "rider": _MOCK_RIDERS["R-012"],
            },
        ],
        "borrowed_entries": [
            {"id": "B-4421-01", "container_key": "round_8gal", "container_label": "Round 8gal", "outstanding": 1, "rider": _MOCK_RIDERS["R-012"]},
            {"id": "B-4421-02", "container_key": "slim_8gal",  "container_label": "Slim 8gal",  "outstanding": 1, "rider": _MOCK_RIDERS["R-012"]},
        ],
    },
    "HY-5530": {
        "credit_lines": [
            {
                "id": "CL-5530-01",
                "product": "Round 8gal — Refill",
                "qty_credited": 4,
                "qty_remaining": 4,
                "unit_price": "₱90.00",
                "total_credit": "₱360.00",
                "rider": _MOCK_RIDERS["R-004"],
            },
            {
                "id": "CL-5530-02",
                "product": "Round 8gal — Refill",
                "qty_credited": 2,
                "qty_remaining": 2,
                "unit_price": "₱90.00",
                "total_credit": "₱180.00",
                "rider": _MOCK_RIDERS["R-001"],
            },
        ],
        "borrowed_entries": [
            {"id": "B-5530-01", "container_key": "round_8gal", "container_label": "Round 8gal", "outstanding": 4, "rider": _MOCK_RIDERS["R-004"]},
            {"id": "B-5530-02", "container_key": "round_8gal", "container_label": "Round 8gal", "outstanding": 2, "rider": _MOCK_RIDERS["R-001"]},
        ],
    },
}


def _group_by_rider(items: list[dict]) -> list[dict]:
    """Group a list of credit lines or borrowed entries by rider.

    Returns a list of ``{ rider, items }`` dicts ordered by rider name.
    Each rider appears once even if they handled multiple line items.
    """
    groups: dict[str, dict] = {}
    for item in items:
        rider = item.get("rider")
        if not rider:
            continue
        key = rider["id"]
        if key not in groups:
            groups[key] = {"rider": rider, "items": []}
        groups[key]["items"].append(item)
    return sorted(groups.values(), key=lambda g: g["rider"]["name"])


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def customer_collect_view(request, customer_id: str):
    """
    HTMX endpoint — returns the collect modal partial for a single
    customer. The modal groups borrowed containers and accredited items
    (credit lines) **per rider** so the operator can record collections
    against the specific rider who handled each transaction. This ensures
    commission repayment is credited to the correct individual.

    Triggered by the COLLECT buttons in the customer table, the debt
    management table, and the detail modal footer.
    """
    customers = _mock_customers_data()["customers"]
    customer = next((c for c in customers if c["id"] == customer_id), None)

    if customer is None:
        return HttpResponse("Customer not found.", status=404)

    enrichment = _COLLECT_ENRICHMENT.get(customer_id, {"credit_lines": [], "borrowed_entries": []})
    credit_lines = enrichment.get("credit_lines", [])
    borrowed_entries = enrichment.get("borrowed_entries", [])

    # Group both credit lines and borrowed entries by rider.
    rider_groups = _group_by_rider(credit_lines + borrowed_entries)

    context = {
        "customer": customer,
        "rider_groups": rider_groups,
        "credit_lines": credit_lines,
        "borrowed_entries": borrowed_entries,
    }
    return render(request, "customers/partials/collect_modal.html", context)


# ---------------------------------------------------------------------------
# Sortable customer table (HTMX partial)
# ---------------------------------------------------------------------------
# Maps the ``sort`` query parameter to the mock row key used for ordering.
_SORT_FIELD_MAP: dict[str, str] = {
    "name": "name",
    "debt_balance": "debt_balance_raw",
    "borrowed_total": "borrowed_total",
    "payable_amount": "payable_amount_raw",
    "last_credit": "last_credit_days",
}
_DEFAULT_SORT = "name"
_DEFAULT_DIR = "asc"


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def customer_table_view(request):
    """
    HTMX endpoint — returns just the customer table partial, ordered by
    the ``sort`` and ``dir`` query parameters.

    Supported sort fields: ``name``, ``debt_balance``, ``borrowed_total``,
    ``payable_amount``, ``last_credit``. Direction is ``asc`` or ``desc``.
    The table column headers issue HTMX GETs to this endpoint, swapping
    ``#customer-table`` in place.
    """
    sort_field = request.GET.get("sort", _DEFAULT_SORT)
    sort_key = _SORT_FIELD_MAP.get(sort_field, _SORT_FIELD_MAP[_DEFAULT_SORT])
    direction = request.GET.get("dir", _DEFAULT_DIR)
    reverse = direction == "desc"

    data = _mock_customers_data()
    customers = sorted(data["customers"], key=lambda c: c.get(sort_key, 0), reverse=reverse)

    # Accent classes for the stats row (kept so the partial renders fully).
    for stat in data["stats"]:
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]

    # Sort-state metadata consumed by the header buttons to render the
    # active arrow and flip direction on the next click.
    next_dir = "desc" if direction == "asc" else "asc"
    sort_state = {
        "field": sort_field,
        "direction": direction,
        "next_dir": next_dir,
    }

    context = {
        "filters": data["filters"],
        "customers": customers,
        "pagination": data["pagination"],
        "sort_state": sort_state,
    }
    return render(request, "customers/partials/customer_table.html", context)


# ---------------------------------------------------------------------------
# Add customer (HTMX modal + POST handler)
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def customer_add_view(request):
    """
    HTMX endpoint — returns the add-customer modal partial.

    The "Add Customer" button in the Summary tab issues an HTMX GET that
    swaps this modal into ``#modal-root``. The form inside POSTs to
    :func:`customer_add_submit_view`.
    """
    return render(request, "customers/partials/add_customer_modal.html")


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def customer_add_submit_view(request):
    """
    HTMX endpoint — handles the add-customer form submission.

    Validates required fields (name) and returns a success toast via an
    OOB swap into ``#toast-container``. The modal is closed by a
    ``<script>`` tag in the response that dispatches ``close-modal``.

    Currently a prototype: no database write occurs. When the real
    ``create_customer`` service lands, wire it here.
    """
    name = (request.POST.get("name") or "").strip()
    if not name:
        return render(
            request,
            "customers/partials/form_error.html",
            {"message": "Customer name is required."},
            status=400,
        )

    return render(
        request,
        "customers/partials/form_success.html",
        {"message": f"Customer \"{name}\" added successfully."},
    )


# ---------------------------------------------------------------------------
# Record debt / credit (HTMX modal + POST handler)
# ---------------------------------------------------------------------------
# Mock product catalogue for the record-debt dropdown. Kept here (not
# imported from apps.products) to avoid cross-app coupling at the
# prototype stage. When real selectors land, replace with a
# ``get_active_products()`` selector call.
_MOCK_PRODUCTS: list[dict] = [
    {"key": "5gal_alk_round", "label": "Alkaline Water — 5-Gallon Round", "unit_price": "40.00"},
    {"key": "5gal_mineral_slim", "label": "Mineral Water — 5-Gallon Slim", "unit_price": "35.00"},
    {"key": "1gal_dispenser", "label": "Purified Drinking Water — 1-Gallon Dispenser", "unit_price": "65.00"},
    {"key": "350ml_case", "label": "PET Bottles — 350ml Case (24 pcs)", "unit_price": "120.00"},
]


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def record_debt_view(request):
    """
    HTMX endpoint — returns the record-debt modal partial.

    The "Record Debt" button in the Debt Management tab issues an HTMX
    GET that swaps this modal into ``#modal-root``. The modal lets the
    operator select a customer and a product, enter quantity credited
    and unit price, and submit to record a new credit line.
    """
    customers = _mock_customers_data()["customers"]
    context = {
        "customers": customers,
        "products": _MOCK_PRODUCTS,
    }
    return render(request, "customers/partials/record_debt_modal.html", context)


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def record_debt_submit_view(request):
    """
    HTMX endpoint — handles the record-debt form submission.

    Validates that a customer and product were selected and that the
    quantity is a positive integer. Returns a success toast on valid
    input, or an error fragment on validation failure.
    """
    customer_id = (request.POST.get("customer_id") or "").strip()
    product_key = (request.POST.get("product_key") or "").strip()
    qty_raw = (request.POST.get("qty_credited") or "").strip()

    if not customer_id:
        return render(request, "customers/partials/form_error.html",
                      {"message": "Please select a customer."}, status=400)
    if not product_key:
        return render(request, "customers/partials/form_error.html",
                      {"message": "Please select a product."}, status=400)
    try:
        qty = int(qty_raw)
    except ValueError:
        return render(request, "customers/partials/form_error.html",
                      {"message": "Quantity must be a whole number."}, status=400)
    if qty <= 0:
        return render(request, "customers/partials/form_error.html",
                      {"message": "Quantity must be greater than zero."}, status=400)

    return render(
        request,
        "customers/partials/form_success.html",
        {"message": f"Recorded {qty} credited unit(s) for {customer_id}."},
    )


# ---------------------------------------------------------------------------
# Record borrowed item (HTMX modal + POST handler)
# ---------------------------------------------------------------------------
_MOCK_CONTAINER_TYPES: list[dict] = [
    {"key": "round_8gal", "label": "Round 8gal"},
    {"key": "slim_8gal", "label": "Slim 8gal"},
    {"key": "other", "label": "Other"},
]


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def record_borrowed_view(request):
    """
    HTMX endpoint — returns the record-borrowed-item modal partial.

    The "Record Borrowed" button in the Debt Management tab issues an
    HTMX GET that swaps this modal into ``#modal-root``. The modal lets
    the operator select a customer and a container type, enter the
    quantity borrowed, and submit to record a new borrowed-container
    entry.
    """
    customers = _mock_customers_data()["customers"]
    context = {
        "customers": customers,
        "container_types": _MOCK_CONTAINER_TYPES,
    }
    return render(request, "customers/partials/record_borrowed_modal.html", context)


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def record_borrowed_submit_view(request):
    """
    HTMX endpoint — handles the record-borrowed-item form submission.

    Validates that a customer and container type were selected and that
    the quantity is a positive integer. Returns a success toast on valid
    input, or an error fragment on validation failure.
    """
    customer_id = (request.POST.get("customer_id") or "").strip()
    container_key = (request.POST.get("container_key") or "").strip()
    qty_raw = (request.POST.get("qty_borrowed") or "").strip()

    if not customer_id:
        return render(request, "customers/partials/form_error.html",
                      {"message": "Please select a customer."}, status=400)
    if not container_key:
        return render(request, "customers/partials/form_error.html",
                      {"message": "Please select a container type."}, status=400)
    try:
        qty = int(qty_raw)
    except ValueError:
        return render(request, "customers/partials/form_error.html",
                      {"message": "Quantity must be a whole number."}, status=400)
    if qty <= 0:
        return render(request, "customers/partials/form_error.html",
                      {"message": "Quantity must be greater than zero."}, status=400)

    return render(
        request,
        "customers/partials/form_success.html",
        {"message": f"Recorded {qty} borrowed container(s) for {customer_id}."},
    )


# ---------------------------------------------------------------------------
# Delete customer (HTMX POST handler)
# ---------------------------------------------------------------------------
@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def customer_delete_view(request, customer_id: str):
    """
    HTMX endpoint — deletes (soft-deletes in production) a customer.

    Only allowed when the customer has **no pending borrowed containers
    and no outstanding debt**. The detail modal only renders the Delete
    button when ``can_delete`` is True, but this view re-checks the
    condition server-side to guard against stale modal state.

    Returns a success toast + HTMX redirect to the customer list on
    success, or an error fragment if the customer is not deletable.
    """
    customers = _mock_customers_data()["customers"]
    customer = next((c for c in customers if c["id"] == customer_id), None)

    if customer is None:
        return render(request, "customers/partials/form_error.html",
                      {"message": "Customer not found."}, status=404)

    has_pending = customer["borrowed_total"] > 0 or customer["has_debt"]
    if has_pending:
        return render(
            request,
            "customers/partials/form_error.html",
            {"message": "Cannot delete a customer with pending debt or unreturned containers."},
            status=400,
        )

    response = render(
        request,
        "customers/partials/form_success.html",
        {"message": f"Customer {customer_id} deleted."},
    )
    # Refresh the customer list so the deleted row disappears.
    response["HX-Redirect"] = "/customers/"
    return response
