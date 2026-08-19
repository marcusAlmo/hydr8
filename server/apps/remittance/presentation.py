"""Presentation layer for the Remittance pages.

Transforms raw selector output (Decimals, querysets, model instances,
raw aggregate dicts) into template-ready dictionaries.  All currency
formatting, date formatting, CSS class maps, label strings, and
card-shaped dicts live here — selectors stay focused on read-side
queries.

Views compose selectors with presentation functions.  For complex
page contexts (Add Remittance, Remittance History, read-only summary)
this module provides composed helpers that call selectors internally
and return the finished context dict, so views stay thin.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

from apps.users.presentation import avatar_classes, driver_code, initials

from . import selectors
from .models import (
    Expense,
    Remittance,
    RemittanceRider,
    RemittanceRiderProductLine,
    RemittanceStaff,
    RiderDeduction,
    StaffDeduction,
)

if TYPE_CHECKING:
    from apps.users.models import User


# ---------------------------------------------------------------------------
# Pure formatting helpers
# ---------------------------------------------------------------------------

def peso_float(value) -> float:
    """Coerce a Decimal/float/None to a plain float for JSON output."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return 0.0


def format_peso(value) -> str:
    """Format a Decimal/float as a Philippine peso string."""
    try:
        return f"\u20b1{float(value):,.2f}"
    except (TypeError, ValueError):
        return "\u20b10.00"


_RIDER_TREND_COLORS = [
    "#006591",
    "#505F76",
    "#35AF80",
    "#D97706",
    "#7C3AED",
    "#0EA5E9",
    "#E11D48",
    "#059669",
    "#4F46E5",
    "#EA580C",
    "#0D9488",
    "#B45309",
    "#F59E0B",
    "#6366F1",
    "#8B5CF6",
]


def rider_trend_color(index: int) -> str:
    return _RIDER_TREND_COLORS[index % len(_RIDER_TREND_COLORS)]


# ---------------------------------------------------------------------------
# Dict-shaping functions — take raw data, return template-ready dicts
# ---------------------------------------------------------------------------

def remittance_row(rem: Remittance) -> dict:
    """Build the template-facing dict for a single remittance row.

    Shared by :func:`build_recent_remittances` (list page) and the
    ``update_paid_status`` HTMX endpoint (single-row swap) so both render
    identical markup.
    """
    creator = rem.created_by
    bg, txt = avatar_classes(creator)
    # Total Drivers Remittance = cash riders turned in.  Not stored directly
    # on the Remittance model, so derive it from the stored totals:
    #   net_remittance = total_remitted + other_sales - commission - salary
    #   -> total_remitted = net_remittance - other_sales + commission + salary
    drivers_remittance = (
        rem.net_remittance
        - rem.total_other_sales
        + rem.total_commission
        + rem.total_salary
    )
    # containers_sold / gross_commission_total are annotated by callers via
    # selectors._apply_kpi_annotations().  Fall back to 0 when the annotation
    # is absent (e.g. ad-hoc single lookups without the annotation).
    containers_sold = getattr(rem, "containers_sold_total", 0) or 0
    gross_commission = getattr(rem, "gross_commission_total", None)
    if gross_commission is None:
        gross_commission = rem.total_commission
    return {
        "id": rem.id,
        "date": rem.date.strftime("%Y-%m-%d"),
        "created_by": creator.full_name,
        "initials": initials(creator),
        "avatar_bg": bg,
        "avatar_text": txt,
        "total_sales": f"{rem.total_sales:,.2f}",
        "total_repayments": f"{rem.total_repayments_received:,.2f}",
        "drivers_remittance": f"{drivers_remittance:,.2f}",
        "total_credits": f"{rem.total_credit_sales:,.2f}",
        "total_expenses": f"{rem.total_expenses:,.2f}",
        "net_commissions": f"{rem.total_commission:,.2f}",
        "net_salaries": f"{rem.total_salary:,.2f}",
        "net_salaries_commissions": f"{rem.total_commission + rem.total_salary:,.2f}",
        "net_remittance": f"{rem.net_remittance:,.2f}",
        "gross_commissions": f"{gross_commission:,.2f}",
        "containers_sold": int(containers_sold),
        "net_profit": f"{rem.net_profit:,.2f}",
        "tithes": f"{rem.tithe_amount:,.2f}",
        "offerings": f"{rem.offering_amount:,.2f}",
        "tithes_paid": rem.tithes_paid,
        "offering_paid": rem.offering_paid,
        "unpaid": not (rem.tithes_paid and rem.offering_paid),
        "status": rem.status,
        "is_draft": rem.status == Remittance.StatusChoices.DRAFT,
    }


def build_product_options(products_qs) -> list[dict]:
    """Shape a Product queryset into the dropdown dicts the remittance
    form consumes.
    """
    products: list[dict] = []
    for p in products_qs:
        name = p.name
        if p.variation:
            name = f"{name} - {p.variation}"
        products.append({
            "key": str(p.id),
            "name": name,
            "unit_price": float(p.price),
        })
    return products


def build_rider_options(
    riders_qs,
    product_keys: list[str],
    rate_map: dict[tuple[str, str], float],
) -> list[dict]:
    """Shape active riders into Alpine.js-ready dicts with per-product
    commission rates and empty product lines.
    """
    riders: list[dict] = []
    for idx, rider in enumerate(riders_qs):
        rider_id = str(rider.pk)
        commission_rates = {
            pk: rate_map.get((rider_id, pk), 0.0)
            for pk in product_keys
        }
        riders.append({
            "id": rider_id,
            "name": rider.full_name,
            "vehicle": "Rider",
            "plate": driver_code(rider),
            "selected": idx == 0,
            "commission_rates": commission_rates,
            "commission_override": "",
            "remitted": "",
            "product_lines": [
                {
                    "product_key": pk,
                    "sold": 0,
                }
                for pk in product_keys
            ],
        })
    return riders


def build_staff_options(staff_qs) -> list[dict]:
    """Shape active staff into Alpine.js-ready dicts with daily rate
    and empty deductions.
    """
    staff: list[dict] = []
    for member in staff_qs:
        staff.append({
            "id": str(member.pk),
            "name": member.full_name,
            "daily_rate": float(member.daily_rate or 0),
            "salary_override": "",
            "deductions": [],
        })
    return staff


def shape_draft_state(raw: dict | None) -> dict | None:
    """Convert raw draft data (model instances, Decimals) into the
    form-facing dict the Alpine.js form hydrates from.

    Returns ``None`` when ``raw`` is ``None`` (no matching remittance).
    """
    if raw is None:
        return None

    rider_expenses: dict[str, list[dict]] = {}
    rider_deductions: dict[str, list[dict]] = {}
    rider_commission_overrides: dict[str, str] = {}
    rider_remittances: dict[str, str] = {}

    for rider_id, expenses in raw.get("rider_expenses", {}).items():
        rider_expenses[rider_id] = [
            {"description": exp.description, "amount": str(exp.amount)}
            for exp in expenses
        ]
    for rider_id, deductions in raw.get("rider_deductions", {}).items():
        rider_deductions[rider_id] = [
            {"description": ded.description, "amount": str(ded.amount)}
            for ded in deductions
        ]
    for rider_id, val in raw.get("rider_commission_overrides", {}).items():
        if val is not None:
            rider_commission_overrides[rider_id] = str(val)
    for rider_id, val in raw.get("rider_remittances", {}).items():
        if val is not None:
            rider_remittances[rider_id] = str(val)

    expenses = [
        {
            "description": exp.description,
            "amount": str(exp.amount),
            "confirmed": True,
        }
        for exp in raw.get("expenses", [])
    ]

    staff_data: dict[str, dict] = {}
    for staff_id, data in raw.get("staff_data", {}).items():
        deductions = [
            {"description": d.description, "amount": str(d.amount)}
            for d in data.get("deductions", [])
        ]
        staff_data[staff_id] = {
            "salary_override": str(data["salary_override"]) if data.get("salary_override") is not None else "",
            "deductions": deductions,
        }

    return {
        "rider_sold": raw.get("rider_sold", {}),
        "rider_credited": raw.get("rider_credited", {}),
        "rider_repaid": raw.get("rider_repaid", {}),
        "rider_expenses": rider_expenses,
        "rider_deductions": rider_deductions,
        "rider_commission_overrides": rider_commission_overrides,
        "rider_remittances": rider_remittances,
        "expenses": expenses,
        "staff_data": staff_data,
        "other_sales": float(raw["other_sales"]) if raw.get("other_sales") else 0.0,
        "offering_amount": str(raw["offering_amount"]) if raw.get("offering_amount") else "",
        "total_salary": float(raw["total_salary"]) if raw.get("total_salary") else 0.0,
    }


# ---------------------------------------------------------------------------
# Composed helpers — call selectors for raw data, then shape the result.
# Views call these so they stay thin.
# ---------------------------------------------------------------------------

def build_draft_state(
    user: "User",
    remittance_date: date,
    status: "Remittance.StatusChoices | None" = Remittance.StatusChoices.DRAFT,
) -> dict | None:
    """Load and shape the form-facing state for an existing remittance.

    Composes :func:`selectors.load_draft_state` (raw data) with
    :func:`shape_draft_state` (formatting).
    """
    raw = selectors.load_draft_state(user, remittance_date, status=status)
    return shape_draft_state(raw)


def build_remittance_row(user: "User", remittance_id: int) -> dict | None:
    """Return the template-facing dict for a single remittance, or
    ``None`` if it does not exist or is outside the user's tenant.
    """
    rem = selectors.get_remittance(user, remittance_id)
    return remittance_row(rem) if rem else None


def build_recent_remittances(user: "User", limit: int = 25) -> dict:
    """Return recent remittance rows and the total count for pagination."""
    raw = selectors.get_recent_remittances(user, limit=limit)
    rows = [remittance_row(rem) for rem in raw["remittances"]]
    return {"remittances": rows, "total": raw["total"]}


def build_add_remittance_context(
    user: "User",
    remittance_date: date | None = None,
) -> dict:
    """Build the full context for the Add Remittance page.

    If a DRAFT remittance already exists for the given date (defaulting
    to today), the form is hydrated from the database draft — sold
    quantities, expenses, and offering amount are restored so the user
    can continue editing seamlessly after a "Save as Draft" / page
    refresh cycle, or after clicking "Finalize" from the history page
    for a draft on a different date.
    """
    default_date = remittance_date or timezone.localdate()
    products_qs = selectors.get_product_catalog(user)
    products = build_product_options(products_qs)
    product_keys = [p["key"] for p in products]
    riders_qs = selectors._active_riders_qs(user)
    rate_map = selectors.get_rider_commission_rates(riders_qs, product_keys)
    riders = build_rider_options(riders_qs, product_keys, rate_map)
    staff_qs = selectors._active_staff_qs(user)
    staff = build_staff_options(staff_qs)
    repayments = selectors._repayments_for_date(user, riders_qs, default_date)
    total_credits = selectors._credit_sales_for_date(user, default_date)
    credit_repaid_counts = selectors._credit_and_repaid_counts(
        user, riders_qs, default_date
    )
    company_id = getattr(getattr(user, "company", None), "id", None)

    # Inject credited/repaid counts into each rider's product lines.
    for rider in riders:
        counts = credit_repaid_counts.get(rider["id"], {})
        for line in rider["product_lines"]:
            pk = line["product_key"]
            c = counts.get(pk)
            if c:
                line["credited"] = c["credited"]
                line["repaid"] = c["repaid"]

    # Try to load an existing DRAFT for today.  If found, overlay the
    # saved sold quantities / expenses / offering / staff data onto the
    # fresh rider/staff metadata so the form reflects the persisted state.
    draft_state = build_draft_state(user, default_date)
    has_draft = draft_state is not None
    expenses: list[dict] = []
    offering_amount = ""
    other_sales = 0.0

    if draft_state is not None:
        rider_sold = draft_state["rider_sold"]
        rider_credited = draft_state.get("rider_credited", {})
        rider_repaid = draft_state.get("rider_repaid", {})
        rider_expenses = draft_state.get("rider_expenses", {})
        rider_deductions = draft_state.get("rider_deductions", {})
        rider_commission_overrides = draft_state.get("rider_commission_overrides", {})
        rider_remittances = draft_state.get("rider_remittances", {})
        for rider in riders:
            rid = rider["id"]
            sold_map = rider_sold.get(rid)
            credited_map = rider_credited.get(rid)
            repaid_map = rider_repaid.get(rid)
            if sold_map or credited_map or repaid_map:
                for line in rider["product_lines"]:
                    pk = line["product_key"]
                    if sold_map and sold_map.get(pk) is not None:
                        line["sold"] = sold_map[pk]
                    if credited_map and credited_map.get(pk) is not None:
                        line["credited"] = credited_map[pk]
                    elif sold_map:
                        line["credited"] = 0
                    if repaid_map and repaid_map.get(pk) is not None:
                        line["repaid"] = repaid_map[pk]
                    elif sold_map:
                        line["repaid"] = 0
            rider["expenses"] = rider_expenses.get(rid, [])
            rider["deductions"] = rider_deductions.get(rid, [])
            rider["commission_override"] = rider_commission_overrides.get(rid, "")
            rider["remitted"] = rider_remittances.get(rid, "")
        expenses = draft_state["expenses"]
        offering_amount = draft_state["offering_amount"]
        other_sales = draft_state.get("other_sales", 0.0)

        # Apply draft staff data onto the fresh staff list.
        staff_data = draft_state.get("staff_data", {})
        for member in staff:
            saved = staff_data.get(member["id"])
            if saved:
                member["salary_override"] = saved.get("salary_override", "")
                member["deductions"] = saved.get("deductions", [])

    return {
        "today_date": timezone.localtime().strftime("%A, %b %d, %Y"),
        "default_date": default_date.isoformat(),
        "products": products,
        "riders": riders,
        "staff": staff,
        "repayments": repayments,
        "total_credits": total_credits,
        "other_sales": other_sales,
        "rider_position": f"1 of {len(riders)}" if riders else "0 of 0",
        "summary": {
            "total_sales": "\u20b10.00",
            "total_repayments": "\u20b10.00",
            "net_remittance": "\u20b10.00",
            "tithes": "\u20b10.00",
            "total_expenses": "\u20b10.00",
            "total_commission": "\u20b10.00",
            "manual_offering": "\u20b10.00",
        },
        "expenses": expenses,
        "tithe_rate": selectors._tithe_rate(company_id),
        "offering_amount": offering_amount,
        "has_draft": has_draft,
    }


def build_remittance_summary(
    user: "User",
    target_date: date,
) -> dict | None:
    """Return a full read-only summary of the remittance (draft or
    finalized) for ``target_date``, or ``None`` if no remittance exists.

    Composes :func:`selectors.get_remittance_summary_data` (raw model
    instances) with dict-shaping logic here.
    """
    raw = selectors.get_remittance_summary_data(user, target_date)
    if raw is None:
        return None

    rem = raw["remittance"]
    rider_rows = raw["rider_rows"]
    lines = raw["lines"]
    general_expenses = raw["general_expenses"]
    staff_rows = raw["staff_rows"]

    # --- Riders + product lines + expenses + deductions --------------
    lines_by_rider: dict[int, list[dict]] = {}
    for line in lines:
        rider_id = line.remittance_rider.rider_id
        product = line.product
        product_name = product.name
        if product.variation:
            product_name = f"{product_name} - {product.variation}"
        lines_by_rider.setdefault(rider_id, []).append({
            "product_name": product_name,
            "qty_sold": line.qty_sold,
            "qty_credited": line.qty_credited,
            "borrowed": line.borrowed_items,
            "subtotal_payable": peso_float(line.subtotal_payable),
            "subtotal_commission": peso_float(line.subtotal_commission),
        })

    riders_summary: list[dict] = []
    for rr in rider_rows:
        riders_summary.append({
            "name": rr.rider.full_name,
            "commission_override": peso_float(rr.commission_override) if rr.commission_override is not None else None,
            "remitted": peso_float(rr.remitted) if rr.remitted is not None else None,
            "subtotal_payable": peso_float(rr.subtotal_payable),
            "subtotal_commission": peso_float(rr.subtotal_commission),
            "product_lines": lines_by_rider.get(rr.rider_id, []),
            "expenses": [
                {"description": exp.description, "amount": peso_float(exp.amount)}
                for exp in rr.expenses.all()
            ],
            "deductions": [
                {"description": ded.description, "amount": peso_float(ded.amount)}
                for ded in rr.deductions.all()
            ],
        })

    # --- General (unattributed) expenses -----------------------------
    general_expenses_summary = [
        {"description": exp.description, "amount": peso_float(exp.amount)}
        for exp in general_expenses
    ]

    # --- Staff payments ----------------------------------------------
    staff_summary: list[dict] = []
    for sp in staff_rows:
        staff_summary.append({
            "name": sp.staff.full_name,
            "salary": peso_float(sp.effective_salary),
            "net_pay": peso_float(sp.net_pay),
            "deductions": [
                {"description": d.description, "amount": peso_float(d.amount)}
                for d in StaffDeduction.objects.filter(remittance_staff=sp).order_by("id")
            ],
        })

    finalized_at_str = None
    if rem.finalized_at is not None:
        finalized_at_str = timezone.localtime(rem.finalized_at).strftime("%b %d, %Y %I:%M %p")

    summary = {
        "id": rem.id,
        "status": rem.status,
        "date": rem.date.isoformat(),
        "created_by": rem.created_by.full_name if rem.created_by else "\u2014",
        "finalized_by": rem.finalized_by.full_name if rem.finalized_by else None,
        "finalized_at": finalized_at_str,
        "riders": riders_summary,
        "expenses": general_expenses_summary,
        "staff": staff_summary,
        "totals": {
            "total_sales": peso_float(rem.total_sales),
            "total_credits": peso_float(rem.total_credit_sales),
            "total_commission": peso_float(rem.total_commission),
            "total_salary": peso_float(rem.total_salary),
            "total_expenses": peso_float(rem.total_expenses),
            "other_sales": peso_float(rem.total_other_sales),
            "net_remittance": peso_float(rem.net_remittance),
            "net_profit": peso_float(rem.net_profit),
            "total_repayments": peso_float(rem.total_repayments_received),
            "tithes": peso_float(rem.tithe_amount),
            "offering": peso_float(rem.offering_amount),
        },
    }

    # For drafts, attach the form-facing state so the "Load draft"
    # button can populate the editable form without a second request.
    # For finalized records, attach the same shape under ``form_state``
    # so the Add Remittance page can populate the read-only finalized
    # view (the finalized data is shown in the form fields, disabled).
    if rem.status == Remittance.StatusChoices.DRAFT:
        summary["draft_state"] = build_draft_state(user, target_date)
        summary["form_state"] = None
    else:
        summary["draft_state"] = None
        summary["form_state"] = build_draft_state(
            user, target_date, status=Remittance.StatusChoices.FINALIZED
        )

    return summary


def build_remittance_history_context(user: "User", days: int = 30) -> dict:
    """Build the full page context for the Remittance History page.

    Composes :func:`selectors.get_remittance_history_data` (raw
    aggregates) with chart-series shaping and summary-card formatting.
    """
    raw = selectors.get_remittance_history_data(user, days=days)
    today = raw["today"]
    dates = raw["dates"]
    labels = [d.strftime("%b %d") for d in dates]
    remit_by_date = raw["remit_by_date"]

    total_sales: list[float] = []
    commissions_paid: list[float] = []
    total_repayments: list[float] = []
    total_expenses: list[float] = []
    net_profit: list[float] = []
    tithes: list[float] = []
    offerings: list[float] = []
    for d in dates:
        rem = remit_by_date.get(d)
        total_sales.append(float(rem["total_sales"]) if rem and rem["total_sales"] is not None else 0.0)
        commissions_paid.append(float(rem["total_commission"]) if rem and rem["total_commission"] is not None else 0.0)
        total_repayments.append(float(rem["total_repayments"]) if rem and rem["total_repayments"] is not None else 0.0)
        total_expenses.append(float(rem["total_expenses"]) if rem and rem["total_expenses"] is not None else 0.0)
        net_profit.append(float(rem["net_profit"]) if rem and rem["net_profit"] is not None else 0.0)
        tithes.append(float(rem["tithes"]) if rem and rem["tithes"] is not None else 0.0)
        offerings.append(float(rem["offerings"]) if rem and rem["offerings"] is not None else 0.0)

    outstanding_debt = [float(raw["current_debt"])] * len(dates)

    rider_series: list[dict] = []
    for idx, rider in enumerate(raw["active_riders"]):
        units = [raw["units_by_rider_date"].get((rider.pk, d), 0) for d in dates]
        rider_series.append({
            "name": rider.full_name,
            "color": rider_trend_color(idx),
            "units_sold": units,
        })

    trends = {
        "labels": labels,
        "total_sales": total_sales,
        "outstanding_debt": outstanding_debt,
        "commissions_paid": commissions_paid,
        "total_repayments": total_repayments,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "tithes": tithes,
        "offerings": offerings,
        "riders": rider_series,
    }

    # --- Summary cards -------------------------------------------------------
    mtd_sales = raw["mtd_sales"]
    prev_sales = raw["prev_sales"]

    sales_change_pct = 0.0
    if prev_sales:
        sales_change_pct = round(float((mtd_sales - prev_sales) / prev_sales) * 100)

    unpaid_total = raw["unpaid_tithe"] + raw["unpaid_offering"]
    unpaid_count = raw["unpaid_count"]

    # AI Projected Profit (EOQ)
    projected_eoq = Decimal("0.00")
    if raw["days_elapsed"] > 0:
        projected_eoq = (raw["qtd_net"] / raw["days_elapsed"]) * raw["days_in_quarter"]

    if sales_change_pct > 0:
        sales_badge_icon = "trending_up"
        sales_badge_color = "#10b981"
    elif sales_change_pct < 0:
        sales_badge_icon = "trending_down"
        sales_badge_color = "#ef4444"
    else:
        sales_badge_icon = "trending_flat"
        sales_badge_color = "#6b7280"

    summary_cards = [
        {
            "label": "Total Remittance (MTD)",
            "value": format_peso(mtd_sales),
            "accent_bar": "#10b981" if sales_change_pct >= 0 else "#ef4444",
            "badge_text": f"{sales_change_pct:+.0f}%" if prev_sales else "New",
            "badge_icon": sales_badge_icon,
            "badge_color": sales_badge_color,
        },
        {
            "label": "Unpaid Tithes",
            "value": format_peso(unpaid_total),
            "accent_bar": "#f59e0b",
            "badge_text": f"{unpaid_count} Items",
            "badge_icon": "warning",
            "badge_color": "text-error",
        },
        {
            "label": "Projected Profit (EOQ)",
            "value": format_peso(projected_eoq),
            "accent_bar": "primary",
            "badge_text": "",
            "badge_icon": "trending_up",
            "badge_color": "text-primary",
        },
    ]

    return {
        "today_date": timezone.localtime().strftime("%A, %b %d, %Y"),
        "trends": trends,
        "summary_cards": summary_cards,
    }
