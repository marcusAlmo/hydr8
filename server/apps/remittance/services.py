"""Write-side services for the Remittance app.

Financial remittances are finalized atomically: a ``Remittance`` row,
per-rider ``RemittanceRider`` rows, per-rider-product
``RemittanceRiderProductLine`` rows, and ``Expense`` rows are all created
in a single transaction so a remittance is never partially persisted.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import Product
from apps.customers.models import CreditPayment
from apps.users.models import User, DriverCommission

from .models import Expense, Remittance, RemittanceRider, RemittanceRiderProductLine

if TYPE_CHECKING:
    from apps.users.models import User as UserType

logger = logging.getLogger(__name__)


def _to_decimal(value) -> Decimal:
    """Converts an arbitrary value to Decimal, defaulting to 0.00."""
    if value is None or value == "":
        return Decimal("0.00")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def _active_riders_qs(user: "UserType"):
    """Tenant-scoped active driver users."""
    qs = User.objects.filter(
        role__name__iexact="driver",
        deleted_at__isnull=True,
        is_active=True,
    )
    if not (user.is_superuser or user.company_id is None):
        qs = qs.filter(company_id=user.company_id)
    return qs


def _collect_repayments(
    performed_by: "UserType",
    active_riders,
    remittance_date: date,
) -> dict[int | None, list[tuple[CreditPayment, "Product", Decimal]]]:
    """Returns a mapping of ``care_of_id -> [(credit_payment, product, commission_rate), ...]``
    for ALL CreditPayments collected on ``remittance_date`` that are not
    yet linked to a Remittance — regardless of whether ``care_of`` is a
    driver or a staff member.

    The commission rate is looked up from ``DriverCommission`` for the
    (care_of, product) pair.  If ``care_of`` is not a driver (or has no
    DriverCommission row for the product), the rate defaults to 0.00 —
    staff members do not earn commission on repayments.

    The key is ``care_of_id`` (an int) or ``None`` if the credit line
    has no ``care_of`` set.
    """
    rider_ids = {r.pk for r in active_riders}

    company_id = getattr(performed_by, "company_id", None)
    payments = list(
        CreditPayment.objects
        .filter(
            company_id=company_id,
            remittance__isnull=True,
            created_at__date=remittance_date,
        )
        .select_related("credit_line__product", "credit_line__care_of")
        .order_by("created_at")
    )
    if not payments:
        return {}

    # Pre-fetch commission rates for (rider, product) pairs — only for
    # care_of users who are active drivers.  Staff care_of gets 0.00.
    product_ids = {cp.credit_line.product_id for cp in payments}
    rate_map: dict[tuple[int, int], Decimal] = {}
    if rider_ids and product_ids:
        for row in (
            DriverCommission.objects
            .filter(driver_id__in=rider_ids, product_id__in=product_ids)
            .values("driver_id", "product_id", "rate_per_unit")
        ):
            rate_map[(row["driver_id"], row["product_id"])] = Decimal(row["rate_per_unit"])

    by_care_of: dict[int | None, list[tuple[CreditPayment, Product, Decimal]]] = {}
    for cp in payments:
        care_of_id = cp.credit_line.care_of_id
        product = cp.credit_line.product
        # Only active drivers earn commission; staff/None → 0.00.
        if care_of_id in rider_ids:
            rate = rate_map.get((care_of_id, product.id), Decimal("0.00"))
        else:
            rate = Decimal("0.00")
        by_care_of.setdefault(care_of_id, []).append((cp, product, rate))
    return by_care_of


def _unlink_credit_payments(remittance: Remittance) -> int:
    """Unlinks all CreditPayments from a Remittance (sets ``remittance=None``).

    Used before deleting a DRAFT remittance so the PROTECT FK does not
    block the delete.  Returns the count of unlinked payments.
    """
    count = CreditPayment.objects.filter(remittance=remittance).update(remittance=None)
    if count:
        logger.info(
            "Unlinked %s CreditPayments from Remittance id=%s",
            count,
            remittance.id,
        )
    return count


@transaction.atomic
def create_remittance(
    *,
    performed_by: "UserType",
    riders_data: list[dict],
    expenses_data: list[dict],
    manual_offering,
    tithe_rate,
    remittance_date=None,
    finalize: bool = False,
) -> Remittance:
    """Creates a daily remittance from the client payload.

    When ``finalize`` is ``False`` (the default), the remittance is saved
    as a **draft** — it must be finalized later by an administrator via
    :func:`finalize_remittance`.  When ``finalize`` is ``True``, the
    remittance is created and immediately marked as finalized.

    Raises ``ValidationError`` if a remittance already exists for the
    date, a rider or product cannot be resolved, or any financial total
    is negative.
    """
    company = getattr(performed_by, "company", None)
    remittance_date = remittance_date or timezone.localdate()

    existing = Remittance.objects.filter(company=company, date=remittance_date).first()
    if existing is not None:
        if existing.status == Remittance.StatusChoices.FINALIZED:
            raise ValidationError(
                f"A finalized remittance for {remittance_date} already exists."
            )
        if finalize:
            # A draft was prepared by staff; the admin is now finalizing.
            # Replace the draft with a finalized remittance built from the
            # current (possibly edited) payload — same upsert pattern as
            # ``save_remittance_draft`` so the transition never errors with
            # "a draft already exists".
            _unlink_credit_payments(existing)
            existing.delete()
            logger.info(
                "[%s] Replaced DRAFT id=%s for date=%s prior to finalize",
                performed_by.id,
                existing.id,
                remittance_date,
            )
        else:
            raise ValidationError(
                f"A draft for {remittance_date} already exists. "
                "Use 'Save as Draft' to update it or 'Clear Draft' to remove it."
            )

    return _build_remittance(
        performed_by=performed_by,
        company=company,
        remittance_date=remittance_date,
        riders_data=riders_data,
        expenses_data=expenses_data,
        manual_offering=manual_offering,
        tithe_rate=tithe_rate,
        finalize=finalize,
    )


@transaction.atomic
def save_remittance_draft(
    *,
    performed_by: "UserType",
    riders_data: list[dict],
    expenses_data: list[dict],
    manual_offering,
    tithe_rate,
    remittance_date=None,
) -> Remittance:
    """Creates or replaces a DRAFT remittance for the given date.

    This is the **upsert** variant of :func:`create_remittance` used by
    the "Save as Draft" button so that a staff member can save, refresh,
    edit, and save again without hitting a "already exists" error.

    If a DRAFT already exists for ``(company, date)``, it is deleted
    (cascade to riders, product lines, expenses) and a fresh draft is
    created from the current payload.  If a FINALIZED remittance exists,
    a ``ValidationError`` is raised — finalized records are immutable.

    Returns the newly created :class:`Remittance` instance.
    """
    company = getattr(performed_by, "company", None)
    remittance_date = remittance_date or timezone.localdate()

    existing = Remittance.objects.filter(company=company, date=remittance_date).first()
    if existing is not None:
        if existing.status == Remittance.StatusChoices.FINALIZED:
            raise ValidationError(
                f"A finalized remittance for {remittance_date} already exists "
                "and cannot be overwritten."
            )
        # Unlink CreditPayments before deleting so the PROTECT FK does not
        # block the cascade delete of the draft.
        _unlink_credit_payments(existing)
        # Delete the existing draft (cascade removes children) so we can
        # create a fresh one with the latest form data.
        existing.delete()
        logger.info(
            "[%s] Replaced existing DRAFT for date=%s",
            performed_by.id,
            remittance_date,
        )

    return _build_remittance(
        performed_by=performed_by,
        company=company,
        remittance_date=remittance_date,
        riders_data=riders_data,
        expenses_data=expenses_data,
        manual_offering=manual_offering,
        tithe_rate=tithe_rate,
        finalize=False,
    )


@transaction.atomic
def delete_draft_remittance(
    *,
    performed_by: "UserType",
    remittance_date=None,
) -> bool:
    """Deletes a DRAFT remittance for the given date.

    Used by the "Clear Draft" button to manually discard a saved draft
    and its child records (riders, product lines, expenses).

    If no remittance exists for the date, this is a no-op (returns
    ``False``).  If a FINALIZED remittance exists, raises
    ``ValidationError`` — finalized records must never be deleted.

    Returns ``True`` if a draft was deleted, ``False`` if nothing was
    found.
    """
    company = getattr(performed_by, "company", None)
    remittance_date = remittance_date or timezone.localdate()

    existing = Remittance.objects.filter(company=company, date=remittance_date).first()
    if existing is None:
        return False

    if existing.status == Remittance.StatusChoices.FINALIZED:
        raise ValidationError(
            "Cannot delete a finalized remittance. "
            "Finalized records are immutable."
        )

    # Unlink CreditPayments before deleting so the PROTECT FK does not
    # block the cascade delete of the draft.
    _unlink_credit_payments(existing)
    existing.delete()
    logger.info(
        "[%s] Cleared DRAFT remittance for date=%s",
        performed_by.id,
        remittance_date,
    )
    return True


def _build_remittance(
    *,
    performed_by: "UserType",
    company,
    remittance_date,
    riders_data: list[dict],
    expenses_data: list[dict],
    manual_offering,
    tithe_rate,
    finalize: bool = False,
) -> Remittance:
    """Shared core that creates a Remittance row and all child records.

    Called by :func:`create_remittance` (new date) and
    :func:`save_remittance_draft` (upsert after deleting the prior draft).
    """
    # --- Resolve products referenced by the payload ------------------------
    product_ids: set[str] = set()
    for rider in riders_data:
        for line in rider.get("product_lines", []):
            product_ids.add(line.get("product_key"))

    products = {
        str(p.id): p
        for p in Product.objects.for_user(performed_by).filter(id__in=product_ids)
    }
    missing_products = product_ids - set(products.keys())
    if missing_products:
        raise ValidationError(f"Unknown product(s): {', '.join(missing_products)}")

    # --- Create the parent Remittance row ---------------------------------
    # The parent is always created as DRAFT first so the DB immutability
    # trigger (migration 0005) does not block the child-row INSERTs that
    # follow.  When ``finalize`` is True the status is flipped to FINALIZED
    # in the final save below, after every child has been persisted.
    remittance = Remittance.objects.create(
        date=remittance_date,
        company=company,
        created_by=performed_by,
        status=Remittance.StatusChoices.DRAFT,
        tithe_rate_snapshot=_to_decimal(tithe_rate),
        offering_amount=_to_decimal(manual_offering),
    )

    total_sales = Decimal("0.00")
    total_credit_sales = Decimal("0.00")
    total_commission = Decimal("0.00")
    total_expenses = Decimal("0.00")
    total_borrowed_items = 0
    total_repayments = Decimal("0.00")

    active_riders = _active_riders_qs(performed_by)
    active_rider_list = list(active_riders)
    rider_id_set = {r.pk for r in active_rider_list}

    # Collect ALL repayments collected on the remittance date and not yet
    # linked to a Remittance — regardless of whether care_of is a driver
    # or staff.  Driver-attributed repayments earn commission; staff do not.
    repayments_by_care_of = _collect_repayments(
        performed_by, active_rider_list, remittance_date
    )

    # Map rider_id -> RemittanceRider for repayment attribution.
    rider_rows: dict[int, RemittanceRider] = {}

    for rider_payload in riders_data:
        rider_id = rider_payload.get("id")
        rider = active_riders.filter(id=rider_id).first()
        if not rider:
            raise ValidationError(f"Rider not found or inactive: {rider_id}")

        remittance_rider = RemittanceRider.objects.create(
            remittance=remittance,
            rider=rider,
            company=company,
            subtotal_payable=Decimal("0.00"),
            subtotal_commission=Decimal("0.00"),
        )
        rider_rows[rider.id] = remittance_rider

        rider_payable = Decimal("0.00")
        rider_commission = Decimal("0.00")

        for line in rider_payload.get("product_lines", []):
            product_key = line.get("product_key")
            product = products.get(product_key)
            if product is None:
                continue

            sold = int(line.get("sold") or 0)
            credited = int(line.get("credited") or 0)
            borrowed = int(line.get("borrowed") or 0)

            if sold < 0 or credited < 0 or borrowed < 0:
                raise ValidationError("Quantities cannot be negative.")

            paid = max(0, sold - credited)

            commission_rate = Decimal("0.00")
            commission = DriverCommission.objects.filter(
                driver=rider, product=product
            ).first()
            if commission is not None:
                commission_rate = commission.rate_per_unit

            unit_price = product.price
            payable = Decimal(paid) * unit_price
            credit_total = Decimal(credited) * unit_price
            line_commission = Decimal(paid) * commission_rate

            # Skip purely empty lines, but persist any line with activity.
            if paid == 0 and credited == 0 and borrowed == 0:
                continue

            RemittanceRiderProductLine.objects.create(
                remittance_rider=remittance_rider,
                product=product,
                company=company,
                qty_sold=sold,
                qty_credited=credited,
                borrowed_items=borrowed,
                unit_price_snapshot=unit_price,
                commission_rate_snapshot=commission_rate,
                subtotal_payable=payable,
                subtotal_credit=credit_total,
                subtotal_commission=line_commission,
            )

            rider_payable += payable
            rider_commission += line_commission
            total_credit_sales += credit_total
            total_borrowed_items += borrowed

        # Add repayment commission for this rider (collected today for
        # credits they previously extended).  The repayment amounts
        # themselves are tracked separately in total_repayments.
        rider_repayment_commission = Decimal("0.00")
        for cp, _product, rate in repayments_by_care_of.get(rider.id, []):
            rider_repayment_commission += Decimal(cp.containers_paid) * rate
        rider_commission += rider_repayment_commission

        # Apply a rider-level commission override if provided.
        override = rider_payload.get("commission_override")
        if override not in (None, ""):
            rider_commission = _to_decimal(override)

        remittance_rider.subtotal_payable = rider_payable
        remittance_rider.subtotal_commission = rider_commission
        remittance_rider.save(
            update_fields=["subtotal_payable", "subtotal_commission", "updated_at"]
        )

        total_sales += rider_payable
        total_commission += rider_commission

    # Link ALL CreditPayments to this remittance and accumulate total
    # repayments.  Payments attributed to active riders (via care_of)
    # earn commission; payments attributed to staff or with no care_of
    # are still linked and counted in total_repayments but earn no
    # commission.  Rider-attributed payments for riders not in the
    # payload get a lightweight RemittanceRider row.
    for care_of_id, entries in repayments_by_care_of.items():
        # Link the payments regardless of who care_of is.
        payment_ids = [cp.id for cp, _p, _r in entries]
        CreditPayment.objects.filter(id__in=payment_ids).update(remittance=remittance)
        for cp, _p, _r in entries:
            total_repayments += cp.amount

        # Only active drivers earn repayment commission.  Skip staff/None.
        if care_of_id not in rider_id_set:
            continue

        rr = rider_rows.get(care_of_id)
        if rr is None:
            # Rider not in the payload — create a lightweight row to hold
            # their repayment commission.
            rider = next((r for r in active_rider_list if r.id == care_of_id), None)
            if rider is None:
                continue
            rr = RemittanceRider.objects.create(
                remittance=remittance,
                rider=rider,
                company=company,
                subtotal_payable=Decimal("0.00"),
                subtotal_commission=Decimal("0.00"),
            )
            rider_rows[care_of_id] = rr
            rider_repayment_commission = Decimal("0.00")
            for cp, _product, rate in entries:
                rider_repayment_commission += Decimal(cp.containers_paid) * rate
            rr.subtotal_commission = rider_repayment_commission
            rr.save(update_fields=["subtotal_commission", "updated_at"])
            total_commission += rider_repayment_commission

    for expense in expenses_data:
        amount = _to_decimal(expense.get("amount"))
        description = (expense.get("description") or "").strip()
        if not description and amount == 0:
            continue
        if amount < 0:
            raise ValidationError("Expense amounts cannot be negative.")

        Expense.objects.create(
            remittance=remittance,
            description=description or "(unnamed)",
            amount=amount,
            company=company,
            recorded_by=performed_by,
        )
        total_expenses += amount

    net_profit = total_sales + total_repayments - total_expenses - total_commission
    tithe_amount = net_profit * remittance.tithe_rate_snapshot

    remittance.total_sales = total_sales
    remittance.total_credit_sales = total_credit_sales
    remittance.total_commission = total_commission
    remittance.total_expenses = total_expenses
    remittance.total_borrowed_items = total_borrowed_items
    remittance.total_repayments_received = total_repayments
    remittance.net_profit = net_profit
    remittance.tithe_amount = tithe_amount

    # Flip DRAFT -> FINALIZED as the final atomic step.  At this point
    # every child row has been persisted, so the DB immutability trigger
    # (which only fires when OLD.status = 'FINALIZED') does not block us.
    finalize_fields: list[str] = []
    if finalize:
        remittance.status = Remittance.StatusChoices.FINALIZED
        remittance.finalized_by = performed_by
        remittance.finalized_at = timezone.now()
        finalize_fields = ["status", "finalized_by", "finalized_at"]

    remittance.save(
        update_fields=[
            "total_sales",
            "total_credit_sales",
            "total_commission",
            "total_expenses",
            "total_borrowed_items",
            "total_repayments_received",
            "net_profit",
            "tithe_amount",
            *finalize_fields,
            "updated_at",
        ]
    )

    logger.info(
        "[%s] Created Remittance id=%s company_id=%s total_sales=%s "
        "total_repayments=%s net_profit=%s",
        performed_by.id,
        remittance.id,
        getattr(company, "id", None),
        total_sales,
        total_repayments,
        net_profit,
    )
    return remittance


@transaction.atomic
def update_remittance_paid_status(
    *,
    performed_by: "UserType",
    remittance_id: int,
    tithes_paid: bool,
    offering_paid: bool,
) -> Remittance:
    """Updates the ``tithes_paid`` / ``offering_paid`` flags on a finalized
    remittance.

    Tenant-scoped via ``Remittance.objects.for_user`` so a user can only
    mutate remittances belonging to their own company. Raises
    ``ValidationError`` if the remittance does not exist.

    Returns the refreshed :class:`Remittance` instance.
    """
    remittance = (
        Remittance.objects
        .for_user(performed_by)
        .select_related("created_by")
        .filter(id=remittance_id)
        .first()
    )
    if remittance is None:
        raise ValidationError("Remittance not found.")

    remittance.tithes_paid = tithes_paid
    remittance.offering_paid = offering_paid
    remittance.save(update_fields=["tithes_paid", "offering_paid", "updated_at"])

    logger.info(
        "[%s] Updated Remittance id=%s tithes_paid=%s offering_paid=%s",
        performed_by.id,
        remittance.id,
        tithes_paid,
        offering_paid,
    )
    return remittance


def is_admin_user(user: "UserType") -> bool:
    """Returns True if the user has the Admin role (or is a superuser)."""
    return bool(
        user.is_superuser
        or (getattr(user, "role", None) is not None and user.role.name == "Admin")
    )


@transaction.atomic
def finalize_remittance(
    *,
    performed_by: "UserType",
    remittance_id: int,
    pin: str,
) -> Remittance:
    """Finalizes a DRAFT remittance.

    Requires the ``Admin`` role (or superuser) and a valid PIN.  The PIN
    is verified against ``performed_by.check_pin`` so any admin can
    finalize a draft prepared by any staff member.

    Raises ``ValidationError`` if:
      - the user is not an admin
      - the PIN is incorrect
      - the remittance does not exist (or is outside the user's tenant)
      - the remittance is already finalized

    Returns the refreshed :class:`Remittance` instance.
    """
    if not is_admin_user(performed_by):
        raise ValidationError("Only administrators can finalize remittances.")

    if not performed_by.check_pin(pin or ""):
        raise ValidationError("Incorrect PIN.")

    remittance = (
        Remittance.objects
        .for_user(performed_by)
        .select_related("created_by")
        .filter(id=remittance_id)
        .first()
    )
    if remittance is None:
        raise ValidationError("Remittance not found.")

    if remittance.status == Remittance.StatusChoices.FINALIZED:
        raise ValidationError("Remittance is already finalized.")

    remittance.status = Remittance.StatusChoices.FINALIZED
    remittance.finalized_by = performed_by
    remittance.finalized_at = timezone.now()
    remittance.save(
        update_fields=["status", "finalized_by", "finalized_at", "updated_at"]
    )

    logger.info(
        "[%s] Finalized Remittance id=%s (created_by=%s)",
        performed_by.id,
        remittance.id,
        remittance.created_by_id,
    )
    return remittance
