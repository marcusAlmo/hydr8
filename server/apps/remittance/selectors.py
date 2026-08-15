"""Read-side selectors for the Remittance pages.

Selectors return dicts shaped for the ``add_remittance.html`` and
``remittance_history.html`` templates.  Views call these — they never hit
the ORM directly.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from django.db.models import Prefetch, Q, Sum
from django.utils import timezone

from apps.core.models import Product, SystemConfig
from apps.customers.models import CreditLine, CreditPayment, Customer
from apps.users.models import User, DriverCommission
from apps.users.presentation import avatar_classes, driver_code, initials
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
    from apps.users.models import User as UserType

logger = logging.getLogger(__name__)


def _tithe_rate(company_id: int | None) -> float:
    """Returns the tenant-scoped tithe rate (fraction, e.g. 0.10)."""
    qs = SystemConfig.objects.filter(key="tithe_rate")
    row = qs.filter(company_id=company_id).first()
    if row is None:
        row = qs.filter(company_id__isnull=True).first()
    raw = row.value if row is not None else "0.10"
    try:
        return float(Decimal(raw))
    except (InvalidOperation, ValueError, TypeError):
        return 0.10


def list_products_for_remittance(user: "UserType") -> list[dict]:
    """Returns the active product catalogue in the shape the remittance
    form consumes.
    """
    qs = (
        Product.objects
        .for_user(user)
        .filter(deleted_at__isnull=True, deactivated_at__isnull=True)
        .order_by("name", "variation")
    )

    products: list[dict] = []
    for p in qs:
        name = p.name
        if p.variation:
            name = f"{name} - {p.variation}"
        products.append({
            "key": str(p.id),
            "name": name,
            "unit_price": float(p.price),
        })
    return products


def _active_riders_qs(user: "UserType"):
    """Tenant-scoped active driver users."""
    qs = User.objects.filter(
        role__name__iexact="driver",
        deleted_at__isnull=True,
        is_active=True,
        deactivated_at__isnull=True,
    )
    if not (user.is_superuser or user.company_id is None):
        qs = qs.filter(company_id=user.company_id)
    return qs.order_by("first_name", "last_name", "username")


def _credit_sales_for_date(
    user: "UserType",
    remittance_date: date,
) -> float:
    """Returns the total credit sales (CreditLine.total_credit_amount)
    issued on ``remittance_date`` for the user's tenant.

    Credit sales are recorded on the customer's page (Add Credit Record)
    and are not editable on the remittance form.  This value feeds the
    "Total Credits" KPI in the remittance summary.
    """
    company_id = getattr(user, "company_id", None)
    qs = (
        CreditLine.objects
        .filter(
            company_id=company_id,
            transaction_date=remittance_date,
        )
    )
    total = qs.aggregate(total=Sum("total_credit_amount"))["total"]
    return float(total) if total is not None else 0.0


def _credit_and_repaid_counts(
    user: "UserType",
    riders_qs,
    remittance_date: date,
) -> dict[str, dict[str, dict]]:
    """Returns credited and repaid unit counts per (rider, product).

    Returns a nested dict::

        {
            str(rider_id): {
                str(product_id): {
                    "credited": int,   # units credited today by this rider
                    "repaid": int,     # units repaid today for this rider+product
                },
                ...
            },
            ...
        }

    Credited counts come from ``CreditLine`` records whose
    ``transaction_date`` is ``remittance_date`` and where ``care_of`` is an
    active rider.  Repaid counts come from ``CreditPayment`` records whose
    ``paid_at`` is ``remittance_date`` (falling back to ``created_at__date``
    for legacy records) and that are linked to credit lines whose
    ``care_of`` is an active rider.
    """
    rider_ids = {r.pk for r in riders_qs}
    company_id = getattr(user, "company_id", None)

    result: dict[str, dict[str, dict]] = {}

    # --- Credited units today (CreditLine.qty_credited) ---
    credit_lines = (
        CreditLine.objects
        .filter(
            company_id=company_id,
            transaction_date=remittance_date,
            care_of_id__in=rider_ids,
        )
        .values("care_of_id", "product_id", "qty_credited")
    )
    for cl in credit_lines:
        rider_id = str(cl["care_of_id"])
        product_id = str(cl["product_id"])
        result.setdefault(rider_id, {}).setdefault(product_id, {"credited": 0, "repaid": 0})
        result[rider_id][product_id]["credited"] += cl["qty_credited"]

    # --- Repaid units today (CreditPayment.containers_paid) ---
    payments = (
        CreditPayment.objects
        .filter(
            company_id=company_id,
            credit_line__care_of_id__in=rider_ids,
        )
        .filter(
            Q(paid_at=remittance_date)
            | Q(paid_at__isnull=True, created_at__date=remittance_date)
        )
        .filter(
            Q(remittance__isnull=True)
            | Q(
                remittance__status=Remittance.StatusChoices.DRAFT,
                remittance__date=remittance_date,
            )
        )
        .values("credit_line__care_of_id", "credit_line__product_id", "containers_paid")
    )
    for cp in payments:
        rider_id = str(cp["credit_line__care_of_id"])
        product_id = str(cp["credit_line__product_id"])
        result.setdefault(rider_id, {}).setdefault(product_id, {"credited": 0, "repaid": 0})
        result[rider_id][product_id]["repaid"] += cp["containers_paid"]

    return result


def _repayments_for_date(
    user: "UserType",
    riders_qs,
    remittance_date: date,
) -> list[dict]:
    """Returns a flat list of ALL CreditPayments collected on
    ``remittance_date`` that are either unlinked OR linked to a DRAFT
    remittance for the same date — regardless of who the ``care_of`` is
    (rider or staff).

    Payments linked to a FINALIZED remittance are excluded (they are
    locked and should not reappear on the Add Remittance form).

    The ``paid_at`` date is used when set; otherwise the legacy
    ``created_at__date`` fallback is used.

    Each entry is shaped for the Alpine.js form::

        {
            "payer": str,           # customer name
            "product_key": str,     # product FK as string
            "qty": int,             # containers_paid
            "amount": float,        # payment amount
            "care_of_id": str,      # care_of user FK as string (or "")
            "care_of_name": str,    # care_of user full name (or "—")
            "care_of_is_driver": bool,  # True if care_of is an active driver
        }

    ``riders_qs`` is used only to determine which ``care_of`` users are
    active drivers (so the frontend knows whether to compute commission).
    """
    rider_ids = {r.pk for r in riders_qs}
    company_id = getattr(user, "company_id", None)

    qs = (
        CreditPayment.objects
        .filter(
            company_id=company_id,
        )
        .filter(
            Q(paid_at=remittance_date)
            | Q(paid_at__isnull=True, created_at__date=remittance_date)
        )
        .filter(
            Q(remittance__isnull=True)
            | Q(
                remittance__status=Remittance.StatusChoices.DRAFT,
                remittance__date=remittance_date,
            )
        )
        .select_related("credit_line__customer", "credit_line__product", "credit_line__care_of")
        .order_by("paid_at", "created_at")
    )

    repayments: list[dict] = []
    for cp in qs:
        care_of = cp.credit_line.care_of
        care_of_id = str(care_of.pk) if care_of else ""
        care_of_name = care_of.full_name if care_of else "—"
        repayments.append({
            "payer": cp.credit_line.customer.name,
            "product_key": str(cp.credit_line.product_id),
            "qty": cp.containers_paid,
            "amount": float(cp.amount),
            "care_of_id": care_of_id,
            "care_of_name": care_of_name,
            "care_of_is_driver": care_of_id in {str(rid) for rid in rider_ids},
        })
    return repayments


def list_riders_for_remittance(
    user: "UserType",
    remittance_date: date | None = None,
) -> list[dict]:
    """Returns active riders with per-product commission rates and empty
    product lines, ready for Alpine.js to hydrate.

    Repayments are NO LONGER embedded per-rider — they are returned as a
    separate flat list by :func:`_repayments_for_date` and injected into
    the page context at the top level.
    """
    remittance_date = remittance_date or timezone.localdate()
    products = list_products_for_remittance(user)
    product_keys = [p["key"] for p in products]
    riders_qs = _active_riders_qs(user)

    # Pre-fetch commission rates for (rider, product) pairs.
    rate_map: dict[tuple[str, str], float] = {}
    if riders_qs and product_keys:
        commissions = DriverCommission.objects.filter(
            driver__in=riders_qs,
            product_id__in=product_keys,
        ).values("driver_id", "product_id", "rate_per_unit")
        for row in commissions:
            rate_map[(str(row["driver_id"]), str(row["product_id"]))] = float(
                row["rate_per_unit"]
            )

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


def _active_staff_qs(user: "UserType"):
    """Tenant-scoped active staff users (Role == 'Staff')."""
    qs = User.objects.filter(
        role__name__iexact="Staff",
        deleted_at__isnull=True,
        is_active=True,
        deactivated_at__isnull=True,
    )
    if not (user.is_superuser or user.company_id is None):
        qs = qs.filter(company_id=user.company_id)
    return qs.order_by("first_name", "last_name", "username")


def list_staff_for_remittance(user: "UserType") -> list[dict]:
    """Returns active staff with their daily rate, ready for Alpine.js
    to hydrate the staff payment tab.

    Each entry is shaped::

        {
            "id": str,
            "name": str,
            "daily_rate": float,
            "salary_override": "",
            "deductions": [],
        }
    """
    staff_qs = _active_staff_qs(user)
    staff: list[dict] = []
    for idx, member in enumerate(staff_qs):
        staff.append({
            "id": str(member.pk),
            "name": member.full_name,
            "daily_rate": float(member.daily_rate or 0),
            "salary_override": "",
            "deductions": [],
        })
    return staff


def _load_draft_state(
    user: "UserType",
    remittance_date: date,
    status: "Remittance.StatusChoices | None" = Remittance.StatusChoices.DRAFT,
) -> dict | None:
    """Loads an existing remittance for ``remittance_date`` and returns its
    form-facing state, or ``None`` if no matching record exists.

    By default only ``DRAFT`` remittances are loaded (the Add Remittance
    page hydrates the editable form from a draft).  Pass
    ``status=Remittance.StatusChoices.FINALIZED`` (or ``status=None`` to
    match any status) to load a finalized record's state — used to
    populate the read-only finalized view.

    The returned dict is shaped for direct merging into the Add
    Remittance page context::

        {
            "rider_sold": {str(rider_id): {str(product_id): int(sold)}},
            "rider_expenses": {str(rider_id): [{"description": str, "amount": str}, ...]},
            "rider_deductions": {str(rider_id): [{"description": str, "amount": str}, ...]},
            "rider_commission_overrides": {str(rider_id): str},
            "rider_remittances": {str(rider_id): str},
            "expenses": [{"description": str, "amount": str, "confirmed": bool}, ...],
            "staff_data": {str(staff_id): {"salary_override": str, "deductions": [...]}},
            "other_sales": float,
            "offering_amount": str,
            "total_salary": float,
        }

    Only ``qty_sold`` is restored — the frontend form only edits the
    ``sold`` field per product line.  ``qty_credited`` and
    ``borrowed_items`` are not used by the form and are omitted.
    """
    qs = Remittance.objects.for_user(user).filter(date=remittance_date)
    if status is not None:
        qs = qs.filter(status=status)
    draft = qs.first()
    if draft is None:
        return None

    # Build rider_id -> {product_id -> qty_sold} from the draft's lines.
    rider_sold: dict[str, dict[str, int]] = {}
    rider_expenses: dict[str, list[dict]] = {}
    rider_deductions: dict[str, list[dict]] = {}
    rider_commission_overrides: dict[str, str] = {}
    rider_remittances: dict[str, str] = {}

    rider_rows = (
        RemittanceRider.objects
        .filter(remittance=draft)
        .select_related("rider")
        .prefetch_related(
            Prefetch("expenses", queryset=Expense.objects.order_by("id")),
            Prefetch("deductions", queryset=RiderDeduction.objects.order_by("id")),
        )
    )
    rider_id_to_row: dict[str, RemittanceRider] = {}
    for rr in rider_rows:
        rider_id = str(rr.rider_id)
        rider_id_to_row[rider_id] = rr

    lines = (
        RemittanceRiderProductLine.objects
        .filter(remittance_rider__remittance=draft)
        .select_related("remittance_rider__rider", "product")
    )
    for line in lines:
        rider_id = str(line.remittance_rider.rider_id)
        product_id = str(line.product_id)
        rider_sold.setdefault(rider_id, {})[product_id] = line.qty_sold

    # Load rider-attributed expenses and deductions.  These were
    # prefetched above so .all() on each rr hits the prefetched cache
    # instead of issuing a new query per rider (N+1 → 3 queries total).
    for rider_id, rr in rider_id_to_row.items():
        rider_expenses[rider_id] = [
            {"description": exp.description, "amount": str(exp.amount)}
            for exp in rr.expenses.all().order_by("id")
        ]
        rider_deductions[rider_id] = [
            {"description": ded.description, "amount": str(ded.amount)}
            for ded in rr.deductions.all().order_by("id")
        ]
        if rr.commission_override is not None:
            rider_commission_overrides[rider_id] = str(rr.commission_override)
        if rr.remitted is not None:
            rider_remittances[rider_id] = str(rr.remitted)

    # Load unattributed (general) expenses — those without a remittance_rider.
    expenses = [
        {
            "description": exp.description,
            "amount": str(exp.amount),
            "confirmed": True,
        }
        for exp in (
            Expense.objects
            .filter(remittance=draft, remittance_rider__isnull=True)
            .select_related("recorded_by")
            .order_by("id")
        )
    ]

    # Load staff payment data.
    staff_data: dict[str, dict] = {}
    for sp in RemittanceStaff.objects.filter(remittance=draft).select_related("staff"):
        staff_id = str(sp.staff_id)
        deductions = [
            {"description": d.description, "amount": str(d.amount)}
            for d in StaffDeduction.objects.filter(remittance_staff=sp).order_by("id")
        ]
        staff_data[staff_id] = {
            "salary_override": str(sp.salary_override) if sp.salary_override is not None else "",
            "deductions": deductions,
        }

    return {
        "rider_sold": rider_sold,
        "rider_expenses": rider_expenses,
        "rider_deductions": rider_deductions,
        "rider_commission_overrides": rider_commission_overrides,
        "rider_remittances": rider_remittances,
        "expenses": expenses,
        "staff_data": staff_data,
        "other_sales": float(draft.total_other_sales) if draft.total_other_sales else 0.0,
        "offering_amount": str(draft.offering_amount) if draft.offering_amount else "",
        "total_salary": float(draft.total_salary) if draft.total_salary else 0.0,
    }


def get_add_remittance_context(
    user: "UserType",
    remittance_date: date | None = None,
) -> dict:
    """Builds the full context for the Add Remittance page.

    If a DRAFT remittance already exists for the given date (defaulting
    to today), the form is hydrated from the database draft — sold
    quantities, expenses, and offering amount are restored so the user
    can continue editing seamlessly after a "Save as Draft" / page
    refresh cycle, or after clicking "Finalize" from the history page
    for a draft on a different date.
    """
    default_date = remittance_date or timezone.localdate()
    products = list_products_for_remittance(user)
    riders_qs = _active_riders_qs(user)
    riders = list_riders_for_remittance(user, remittance_date=default_date)
    staff = list_staff_for_remittance(user)
    repayments = _repayments_for_date(user, riders_qs, default_date)
    total_credits = _credit_sales_for_date(user, default_date)
    credit_repaid_counts = _credit_and_repaid_counts(user, riders_qs, default_date)
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
    draft_state = _load_draft_state(user, default_date)
    has_draft = draft_state is not None
    expenses: list[dict] = []
    offering_amount = ""
    other_sales = 0.0

    if draft_state is not None:
        rider_sold = draft_state["rider_sold"]
        rider_expenses = draft_state.get("rider_expenses", {})
        rider_deductions = draft_state.get("rider_deductions", {})
        rider_commission_overrides = draft_state.get("rider_commission_overrides", {})
        rider_remittances = draft_state.get("rider_remittances", {})
        for rider in riders:
            rid = rider["id"]
            sold_map = rider_sold.get(rid)
            if sold_map:
                for line in rider["product_lines"]:
                    cached_sold = sold_map.get(line["product_key"])
                    if cached_sold is not None:
                        line["sold"] = cached_sold
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
            "total_sales": "₱0.00",
            "total_repayments": "₱0.00",
            "net_remittance": "₱0.00",
            "tithes": "₱0.00",
            "total_expenses": "₱0.00",
            "total_commission": "₱0.00",
            "manual_offering": "₱0.00",
        },
        "expenses": expenses,
        "tithe_rate": _tithe_rate(company_id),
        "offering_amount": offering_amount,
        "has_draft": has_draft,
    }


def remittance_exists_for_date(user: "UserType", target_date: date) -> bool:
    """Returns True if a remittance already exists for the given date."""
    return Remittance.objects.for_user(user).filter(date=target_date).exists()


def remittance_status_for_date(user: "UserType", target_date: date) -> str | None:
    """Returns the status ('DRAFT' or 'FINALIZED') of a remittance for the
    given date, or ``None`` if no remittance exists.

    Used by the check-date endpoint so the Add Remittance form can
    distinguish between a draft (user can continue editing / re-save)
    and a finalized record (date is locked).
    """
    rem = (
        Remittance.objects
        .for_user(user)
        .filter(date=target_date)
        .only("status")
        .first()
    )
    return rem.status if rem else None


def get_remittance_date_data(user: "UserType", target_date: date) -> dict:
    """Returns the date-dependent credit data for the Add Remittance form.

    When the user changes the remittance date at the top of the form, the
    credit payments, total credits, and per-rider credited/repaid counts
    must be re-fetched for the newly selected date.  This function
    bundles all three so the ``check-date`` endpoint can return them in
    a single round-trip.

    Returns::

        {
            "repayments": list[dict],          # _repayments_for_date output
            "total_credits": float,            # _credit_sales_for_date output
            "credit_repaid_counts": dict,      # _credit_and_repaid_counts output
        }
    """
    riders_qs = _active_riders_qs(user)
    repayments = _repayments_for_date(user, riders_qs, target_date)
    total_credits = _credit_sales_for_date(user, target_date)
    credit_repaid_counts = _credit_and_repaid_counts(user, riders_qs, target_date)
    return {
        "repayments": repayments,
        "total_credits": total_credits,
        "credit_repaid_counts": credit_repaid_counts,
    }


def _peso_float(value) -> float:
    """Coerce a Decimal/float/None to a plain float for JSON output."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return 0.0


def get_remittance_summary_for_date(user: "UserType", target_date: date) -> dict | None:
    """Returns a full read-only summary of the remittance (draft or
    finalized) for ``target_date``, or ``None`` if no remittance exists.

    The summary is shaped for the Add Remittance page's read-only
    "existing remittance" panel — it includes riders, product lines,
    expenses, deductions, staff payments, and all monetary totals.

    For DRAFT remittances the response also carries a ``draft_state``
    key (the same shape produced by :func:`_load_draft_state`) so the
    frontend "Load draft" button can populate the editable form without
    a second round-trip.  For FINALIZED remittances a ``form_state`` key
    (same shape) is attached instead, so the Add Remittance page can
    populate the read-only finalized view in the form fields.

    Returns::

        {
            "status": "DRAFT" | "FINALIZED",
            "date": "YYYY-MM-DD",
            "created_by": str,
            "finalized_by": str | None,
            "finalized_at": str | None,
            "riders": [
                {
                    "name": str,
                    "commission_override": float | None,
                    "remitted": float | None,
                    "subtotal_payable": float,
                    "subtotal_commission": float,
                    "product_lines": [
                        {
                            "product_name": str,
                            "qty_sold": int,
                            "qty_credited": int,
                            "borrowed": int,
                            "subtotal_payable": float,
                            "subtotal_commission": float,
                        }, ...
                    ],
                    "expenses": [{"description": str, "amount": float}, ...],
                    "deductions": [{"description": str, "amount": float}, ...],
                }, ...
            ],
            "expenses": [{"description": str, "amount": float}, ...],
            "staff": [
                {
                    "name": str,
                    "salary": float,
                    "net_pay": float,
                    "deductions": [{"description": str, "amount": float}, ...],
                }, ...
            ],
            "totals": {
                "total_sales": float,
                "total_credits": float,
                "total_commission": float,
                "total_salary": float,
                "total_expenses": float,
                "other_sales": float,
                "net_remittance": float,
                "net_profit": float,
                "total_repayments": float,
                "tithes": float,
                "offering": float,
            },
            "draft_state": dict | None,   # only for DRAFT
            "form_state": dict | None,    # only for FINALIZED
        }
    """
    rem = (
        Remittance.objects
        .for_user(user)
        .filter(date=target_date)
        .select_related("created_by", "finalized_by")
        .first()
    )
    if rem is None:
        return None

    # --- Riders + product lines + expenses + deductions --------------
    rider_rows = (
        RemittanceRider.objects
        .filter(remittance=rem)
        .select_related("rider")
        .prefetch_related(
            Prefetch("expenses", queryset=Expense.objects.order_by("id")),
            Prefetch("deductions", queryset=RiderDeduction.objects.order_by("id")),
        )
        .order_by("rider__first_name", "rider__last_name")
    )
    rider_id_to_row: dict[int, RemittanceRider] = {rr.rider_id: rr for rr in rider_rows}

    lines = (
        RemittanceRiderProductLine.objects
        .filter(remittance_rider__remittance=rem)
        .select_related("remittance_rider__rider", "product")
        .order_by("remittance_rider__rider__first_name", "product__name", "product__variation")
    )

    riders_summary: list[dict] = []
    # Group product lines by rider.
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
            "subtotal_payable": _peso_float(line.subtotal_payable),
            "subtotal_commission": _peso_float(line.subtotal_commission),
        })

    for rr in rider_rows:
        riders_summary.append({
            "name": rr.rider.full_name,
            "commission_override": _peso_float(rr.commission_override) if rr.commission_override is not None else None,
            "remitted": _peso_float(rr.remitted) if rr.remitted is not None else None,
            "subtotal_payable": _peso_float(rr.subtotal_payable),
            "subtotal_commission": _peso_float(rr.subtotal_commission),
            "product_lines": lines_by_rider.get(rr.rider_id, []),
            "expenses": [
                {"description": exp.description, "amount": _peso_float(exp.amount)}
                for exp in rr.expenses.all()
            ],
            "deductions": [
                {"description": ded.description, "amount": _peso_float(ded.amount)}
                for ded in rr.deductions.all()
            ],
        })

    # --- General (unattributed) expenses -----------------------------
    general_expenses = [
        {"description": exp.description, "amount": _peso_float(exp.amount)}
        for exp in (
            Expense.objects
            .filter(remittance=rem, remittance_rider__isnull=True)
            .order_by("id")
        )
    ]

    # --- Staff payments ----------------------------------------------
    staff_summary: list[dict] = []
    for sp in (
        RemittanceStaff.objects
        .filter(remittance=rem)
        .select_related("staff")
        .order_by("staff__first_name", "staff__last_name")
    ):
        staff_summary.append({
            "name": sp.staff.full_name,
            "salary": _peso_float(sp.effective_salary),
            "net_pay": _peso_float(sp.net_pay),
            "deductions": [
                {"description": d.description, "amount": _peso_float(d.amount)}
                for d in StaffDeduction.objects.filter(remittance_staff=sp).order_by("id")
            ],
        })

    finalized_at_str = None
    if rem.finalized_at is not None:
        finalized_at_str = timezone.localtime(rem.finalized_at).strftime("%b %d, %Y %I:%M %p")

    summary = {
        "status": rem.status,
        "date": rem.date.isoformat(),
        "created_by": rem.created_by.full_name if rem.created_by else "—",
        "finalized_by": rem.finalized_by.full_name if rem.finalized_by else None,
        "finalized_at": finalized_at_str,
        "riders": riders_summary,
        "expenses": general_expenses,
        "staff": staff_summary,
        "totals": {
            "total_sales": _peso_float(rem.total_sales),
            "total_credits": _peso_float(rem.total_credit_sales),
            "total_commission": _peso_float(rem.total_commission),
            "total_salary": _peso_float(rem.total_salary),
            "total_expenses": _peso_float(rem.total_expenses),
            "other_sales": _peso_float(rem.total_other_sales),
            "net_remittance": _peso_float(rem.net_remittance),
            "net_profit": _peso_float(rem.net_profit),
            "total_repayments": _peso_float(rem.total_repayments_received),
            "tithes": _peso_float(rem.tithe_amount),
            "offering": _peso_float(rem.offering_amount),
        },
    }

    # For drafts, attach the form-facing state so the "Load draft"
    # button can populate the editable form without a second request.
    # For finalized records, attach the same shape under ``form_state``
    # so the Add Remittance page can populate the read-only finalized
    # view (the finalized data is shown in the form fields, disabled).
    if rem.status == Remittance.StatusChoices.DRAFT:
        summary["draft_state"] = _load_draft_state(user, target_date)
        summary["form_state"] = None
    else:
        summary["draft_state"] = None
        summary["form_state"] = _load_draft_state(
            user, target_date, status=Remittance.StatusChoices.FINALIZED
        )

    return summary


def _remittance_row(rem: Remittance) -> dict:
    """Builds the template-facing dict for a single remittance row.

    Shared by :func:`get_recent_remittances` (list page) and the
    ``update_paid_status`` HTMX endpoint (single-row swap) so both render
    identical markup.
    """
    creator = rem.created_by
    bg, txt = avatar_classes(creator)
    return {
        "id": rem.id,
        "date": rem.date.strftime("%Y-%m-%d"),
        "created_by": creator.full_name,
        "initials": initials(creator),
        "avatar_bg": bg,
        "avatar_text": txt,
        "total_sales": f"{rem.total_sales:,.2f}",
        "total_repayments": f"{rem.total_repayments_received:,.2f}",
        "total_credits": f"{rem.total_credit_sales:,.2f}",
        "total_expenses": f"{rem.total_expenses:,.2f}",
        "total_commission": f"{rem.total_commission:,.2f}",
        "total_salary": f"{rem.total_salary:,.2f}",
        "net_remittance": f"{rem.net_remittance:,.2f}",
        "net_profit": f"{rem.net_profit:,.2f}",
        "tithes": f"{rem.tithe_amount:,.2f}",
        "offerings": f"{rem.offering_amount:,.2f}",
        "tithes_paid": rem.tithes_paid,
        "offering_paid": rem.offering_paid,
        "unpaid": not (rem.tithes_paid and rem.offering_paid),
        "status": rem.status,
        "is_draft": rem.status == Remittance.StatusChoices.DRAFT,
    }


def get_recent_remittances(user: "UserType", limit: int = 25) -> dict:
    """Returns recent remittance rows and the total count for pagination."""
    qs = (
        Remittance.objects
        .for_user(user)
        .select_related("created_by")
        .order_by("-date")
    )

    rows: list[dict] = [_remittance_row(rem) for rem in qs[:limit]]
    return {"remittances": rows, "total": qs.count()}


def get_remittance_row(user: "UserType", remittance_id: int) -> dict | None:
    """Returns the template-facing dict for a single remittance, or
    ``None`` if it does not exist or is outside the user's tenant."""
    rem = (
        Remittance.objects
        .for_user(user)
        .select_related("created_by")
        .filter(id=remittance_id)
        .first()
    )
    return _remittance_row(rem) if rem else None


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


def _format_peso(value) -> str:
    """Format a Decimal/float as a Philippine peso string."""
    try:
        return f"₱{float(value):,.2f}"
    except (TypeError, ValueError):
        return "₱0.00"


def _rider_trend_color(index: int) -> str:
    return _RIDER_TREND_COLORS[index % len(_RIDER_TREND_COLORS)]


def get_remittance_history_context(user: "UserType", days: int = 30) -> dict:
    """Build the full page context for the Remittance History page from live DB data."""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    dates = [start + timedelta(days=i) for i in range(days)]
    labels = [d.strftime("%b %d") for d in dates]

    remit_rows = (
        Remittance.objects.for_user(user)
        .filter(date__range=(start, today))
        .values("date")
        .annotate(
            total_sales=Sum("total_sales"),
            total_commission=Sum("total_commission"),
            total_repayments=Sum("total_repayments_received"),
            total_expenses=Sum("total_expenses"),
            net_profit=Sum("net_profit"),
            tithes=Sum("tithe_amount"),
            offerings=Sum("offering_amount"),
        )
    )
    remit_by_date: dict[date, dict] = {row["date"]: row for row in remit_rows}

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

    # Outstanding debt — current customer ledger balance (no historical snapshots)
    current_debt = (
        Customer.objects.for_user(user)
        .filter(debt_balance__gt=0)
        .aggregate(Sum("debt_balance"))["debt_balance__sum"]
        or Decimal("0.00")
    )
    outstanding_debt = [float(current_debt)] * days

    # Per-rider units sold over the date range
    active_riders = list(_active_riders_qs(user))
    rider_ids = [r.pk for r in active_riders]

    unit_rows = (
        RemittanceRiderProductLine.objects.for_user(user)
        .filter(
            remittance_rider__remittance__date__range=(start, today),
            remittance_rider__rider_id__in=rider_ids,
        )
        .values(
            "remittance_rider__rider_id",
            "remittance_rider__remittance__date",
        )
        .annotate(total_sold=Sum("qty_sold"))
    )
    units_by_rider_date: dict[tuple[int, date], int] = {
        (row["remittance_rider__rider_id"], row["remittance_rider__remittance__date"]): row["total_sold"]
        for row in unit_rows
    }

    rider_series: list[dict] = []
    for idx, rider in enumerate(active_riders):
        units = [units_by_rider_date.get((rider.pk, d), 0) for d in dates]
        rider_series.append({
            "name": rider.full_name,
            "color": _rider_trend_color(idx),
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
    mtd_start = date(today.year, today.month, 1)
    mtd_sales = (
        Remittance.objects.for_user(user)
        .filter(date__year=today.year, date__month=today.month)
        .aggregate(Sum("total_sales"))["total_sales__sum"]
        or Decimal("0.00")
    )

    prev_month = (mtd_start - timedelta(days=1)).replace(day=1)
    prev_sales = (
        Remittance.objects.for_user(user)
        .filter(date__year=prev_month.year, date__month=prev_month.month)
        .aggregate(Sum("total_sales"))["total_sales__sum"]
        or Decimal("0.00")
    )

    sales_change_pct = 0.0
    if prev_sales:
        sales_change_pct = round(float((mtd_sales - prev_sales) / prev_sales) * 100)

    unpaid_tithe = (
        Remittance.objects.for_user(user)
        .filter(tithes_paid=False)
        .aggregate(Sum("tithe_amount"))["tithe_amount__sum"]
        or Decimal("0.00")
    )
    unpaid_offering = (
        Remittance.objects.for_user(user)
        .filter(offering_paid=False)
        .aggregate(Sum("offering_amount"))["offering_amount__sum"]
        or Decimal("0.00")
    )
    unpaid_total = unpaid_tithe + unpaid_offering
    unpaid_count = Remittance.objects.for_user(user).filter(
        Q(tithes_paid=False) | Q(offering_paid=False)
    ).count()

    # AI Projected Profit (EOQ)
    quarter = (today.month - 1) // 3 + 1
    q_start_month = (quarter - 1) * 3 + 1
    q_end_month = q_start_month + 2
    q_start = date(today.year, q_start_month, 1)
    q_end = date(today.year, q_end_month, monthrange(today.year, q_end_month)[1])
    days_in_quarter = (q_end - q_start).days + 1
    days_elapsed = (today - q_start).days + 1
    qtd_net = (
        Remittance.objects.for_user(user)
        .filter(date__range=(q_start, today))
        .aggregate(Sum("net_profit"))["net_profit__sum"]
        or Decimal("0.00")
    )
    projected_eoq = Decimal("0.00")
    if days_elapsed > 0:
        projected_eoq = (qtd_net / days_elapsed) * days_in_quarter

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
            "value": _format_peso(mtd_sales),
            "accent_bar": "#10b981" if sales_change_pct >= 0 else "#ef4444",
            "badge_text": f"{sales_change_pct:+.0f}%" if prev_sales else "New",
            "badge_icon": sales_badge_icon,
            "badge_color": sales_badge_color,
        },
        {
            "label": "Unpaid Tithes",
            "value": _format_peso(unpaid_total),
            "accent_bar": "#f59e0b",
            "badge_text": f"{unpaid_count} Items",
            "badge_icon": "warning",
            "badge_color": "text-error",
        },
        {
            "label": "Projected Profit (EOQ)",
            "value": _format_peso(projected_eoq),
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
