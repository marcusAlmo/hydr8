"""Read-side selectors for the Remittance pages.

Selectors return raw data — Decimals, querysets, model instances, and
simple aggregates. All template-shaped formatting (currency strings,
CSS classes, card dicts, table rows) lives in ``presentation.py``.
Views compose selectors with presentation functions.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from django.db.models import (
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.models import Product, SystemConfig
from apps.customers.models import CreditLine, CreditPayment, Customer
from apps.users.models import User, DriverCommission
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


def get_product_catalog(user: "UserType"):
    """Return the active product catalogue queryset for the remittance
    form.  Presentation layer shapes this into dropdown dicts.
    """
    return (
        Product.objects
        .for_user(user)
        .filter(deleted_at__isnull=True, deactivated_at__isnull=True)
        .order_by("name", "variation")
    )


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


def get_rider_commission_rates(
    riders_qs,
    product_keys: list[str],
) -> dict[tuple[str, str], float]:
    """Return a ``(rider_id, product_id) -> rate_per_unit`` map for the
    given riders and product keys.
    """
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
    return rate_map


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
            "care_of_name": str,    # care_of user full name (or "\u2014")
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
        care_of_name = care_of.full_name if care_of else "\u2014"
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


def load_draft_state(
    user: "UserType",
    remittance_date: date,
    status: "Remittance.StatusChoices | None" = Remittance.StatusChoices.DRAFT,
) -> dict | None:
    """Load an existing remittance for ``remittance_date`` and return its
    raw form-facing state, or ``None`` if no matching record exists.

    By default only ``DRAFT`` remittances are loaded (the Add Remittance
    page hydrates the editable form from a draft).  Pass
    ``status=Remittance.StatusChoices.FINALIZED`` (or ``status=None`` to
    match any status) to load a finalized record's state — used to
    populate the read-only finalized view.

    The returned dict contains **raw** model instances and Decimals —
    :func:`apps.remittance.presentation.shape_draft_state` converts them
    into the string-formatted dict the Alpine.js form expects.

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
    rider_credited: dict[str, dict[str, int]] = {}
    rider_repaid: dict[str, dict[str, int]] = {}
    rider_expenses: dict[str, list] = {}
    rider_deductions: dict[str, list] = {}
    rider_commission_overrides: dict[str, Decimal | None] = {}
    rider_remittances: dict[str, Decimal | None] = {}

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
        rider_credited.setdefault(rider_id, {})[product_id] = line.qty_credited

    # Load repaid units from CreditPayments linked to this remittance,
    # grouped by (care_of, product).  For DRAFT remittances the
    # _credit_and_repaid_counts selector also returns these (from
    # unlinked / draft-linked payments), but for FINALIZED remittances
    # the payments are locked to the finalized record and excluded from
    # that selector — so we must read them directly here.
    repaid_rows = (
        CreditPayment.objects
        .filter(remittance=draft)
        .values("credit_line__care_of_id", "credit_line__product_id")
        .annotate(total_repaid=Sum("containers_paid"))
    )
    for row in repaid_rows:
        care_of_id = row["credit_line__care_of_id"]
        if care_of_id is None:
            continue
        rider_id = str(care_of_id)
        product_id = str(row["credit_line__product_id"])
        rider_repaid.setdefault(rider_id, {})[product_id] = row["total_repaid"]

    # Load rider-attributed expenses and deductions.  These were
    # prefetched above so .all() on each rr hits the prefetched cache
    # instead of issuing a new query per rider (N+1 -> 3 queries total).
    for rider_id, rr in rider_id_to_row.items():
        rider_expenses[rider_id] = list(rr.expenses.all().order_by("id"))
        rider_deductions[rider_id] = list(rr.deductions.all().order_by("id"))
        rider_commission_overrides[rider_id] = rr.commission_override
        rider_remittances[rider_id] = rr.remitted

    # Load unattributed (general) expenses — those without a remittance_rider.
    general_expenses = list(
        Expense.objects
        .filter(remittance=draft, remittance_rider__isnull=True)
        .select_related("recorded_by")
        .order_by("id")
    )

    # Load staff payment data.
    staff_data: dict[str, dict] = {}
    for sp in RemittanceStaff.objects.filter(remittance=draft).select_related("staff"):
        staff_id = str(sp.staff_id)
        deductions = list(
            StaffDeduction.objects.filter(remittance_staff=sp).order_by("id")
        )
        staff_data[staff_id] = {
            "salary_override": sp.salary_override,
            "deductions": deductions,
        }

    return {
        "rider_sold": rider_sold,
        "rider_credited": rider_credited,
        "rider_repaid": rider_repaid,
        "rider_expenses": rider_expenses,
        "rider_deductions": rider_deductions,
        "rider_commission_overrides": rider_commission_overrides,
        "rider_remittances": rider_remittances,
        "expenses": general_expenses,
        "staff_data": staff_data,
        "other_sales": draft.total_other_sales,
        "offering_amount": draft.offering_amount,
        "total_salary": draft.total_salary,
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


def get_remittance_summary_data(
    user: "UserType",
    target_date: date,
) -> dict | None:
    """Return raw model data for a remittance on ``target_date``, or
    ``None`` if no remittance exists.

    The returned dict contains the ``Remittance`` instance and lists of
    related model objects (rider rows, product lines, general expenses,
    staff rows).  :func:`apps.remittance.presentation.build_remittance_summary`
    shapes this into the template-ready summary dict.
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

    rider_rows = list(
        RemittanceRider.objects
        .filter(remittance=rem)
        .select_related("rider")
        .prefetch_related(
            Prefetch("expenses", queryset=Expense.objects.order_by("id")),
            Prefetch("deductions", queryset=RiderDeduction.objects.order_by("id")),
        )
        .order_by("rider__first_name", "rider__last_name")
    )

    lines = list(
        RemittanceRiderProductLine.objects
        .filter(remittance_rider__remittance=rem)
        .select_related("remittance_rider__rider", "product")
        .order_by("remittance_rider__rider__first_name", "product__name", "product__variation")
    )

    general_expenses = list(
        Expense.objects
        .filter(remittance=rem, remittance_rider__isnull=True)
        .order_by("id")
    )

    staff_rows = list(
        RemittanceStaff.objects
        .filter(remittance=rem)
        .select_related("staff")
        .order_by("staff__first_name", "staff__last_name")
    )

    return {
        "remittance": rem,
        "rider_rows": rider_rows,
        "lines": lines,
        "general_expenses": general_expenses,
        "staff_rows": staff_rows,
    }


def _containers_sold_subquery():
    """Subquery annotating the total qty_sold for a remittance.

    Sums ``qty_sold`` across every rider product line.  Only sold units —
    repaid and credited units are excluded.  Kept as a subquery to avoid the
    cartesian-product inflation that a joined ``Sum`` would cause when other
    multi-row annotations are present.
    """
    return (
        RemittanceRiderProductLine.objects
        .filter(remittance_rider__remittance=OuterRef("pk"))
        .values("remittance_rider__remittance")
        .annotate(total=Sum("qty_sold"))
        .values("total")
    )


def _gross_commission_subquery():
    """Subquery annotating the total gross commission for a remittance.

    Sums ``subtotal_commission`` across every rider (the per-rider gross
    commission before balance & manual deductions).  ``total_commission`` on
    the Remittance model is the *net* commission, so this subquery is needed
    for the "Gross Commissions" KPI.
    """
    return (
        RemittanceRider.objects
        .filter(remittance=OuterRef("pk"))
        .values("remittance")
        .annotate(total=Sum("subtotal_commission"))
        .values("total")
    )


def _apply_kpi_annotations(qs):
    """Annotates a Remittance queryset with the KPI values that are not
    stored directly on the Remittance model.

    Adds ``containers_sold_total`` (int) and ``gross_commission_total``
    (Decimal) so the presentation layer can render the full KPI card
    without extra per-row queries.
    """
    return qs.annotate(
        containers_sold_total=Coalesce(
            Subquery(_containers_sold_subquery(), output_field=IntegerField()),
            0,
        ),
        gross_commission_total=Coalesce(
            Subquery(_gross_commission_subquery()),
            Decimal("0.00"),
        ),
    )


def get_recent_remittances(user: "UserType", limit: int = 25) -> dict:
    """Return raw Remittance instances (KPI-annotated) and the total
    count for pagination.

    The presentation layer shapes each instance into a template-ready
    row dict via :func:`apps.remittance.presentation.remittance_row`.
    """
    qs = _apply_kpi_annotations(
        Remittance.objects
        .for_user(user)
        .select_related("created_by")
        .order_by("-date")
    )
    return {"remittances": list(qs[:limit]), "total": qs.count()}


def get_remittance(user: "UserType", remittance_id: int) -> Remittance | None:
    """Return a single KPI-annotated Remittance, or ``None`` if it does
    not exist or is outside the user's tenant.

    The presentation layer shapes it via
    :func:`apps.remittance.presentation.remittance_row`.
    """
    return (
        _apply_kpi_annotations(
            Remittance.objects
            .for_user(user)
            .select_related("created_by")
        )
        .filter(id=remittance_id)
        .first()
    )


def get_remittance_history_data(user: "UserType", days: int = 30) -> dict:
    """Return raw aggregate data for the Remittance History page.

    :func:`apps.remittance.presentation.build_remittance_history_context`
    shapes this into the template-ready context dict (chart series,
    summary cards).
    """
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    dates = [start + timedelta(days=i) for i in range(days)]

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

    # Outstanding debt — current customer ledger balance (no historical snapshots)
    current_debt = (
        Customer.objects.for_user(user)
        .filter(debt_balance__gt=0)
        .aggregate(Sum("debt_balance"))["debt_balance__sum"]
        or Decimal("0.00")
    )

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

    # --- Summary card aggregates -------------------------------------------
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

    return {
        "today": today,
        "dates": dates,
        "remit_by_date": remit_by_date,
        "current_debt": current_debt,
        "active_riders": active_riders,
        "units_by_rider_date": units_by_rider_date,
        "mtd_sales": mtd_sales,
        "prev_sales": prev_sales,
        "unpaid_tithe": unpaid_tithe,
        "unpaid_offering": unpaid_offering,
        "unpaid_count": unpaid_count,
        "qtd_net": qtd_net,
        "days_in_quarter": days_in_quarter,
        "days_elapsed": days_elapsed,
    }
