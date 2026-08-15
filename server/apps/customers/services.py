"""Write-side services for the Customers app.

All customer mutations (add, debt, borrowed, delete) live here.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest
from django.utils import timezone

from apps.core.models import Product
from apps.settings.selectors import get_default_credit_limit
from apps.users.models import User
from apps.users.permissions import is_admin

from .models import BorrowedContainer, CreditPayment, Customer, CreditLine
from .selectors import _parse_display_id

if TYPE_CHECKING:
    from apps.users.models import User as UserType

logger = logging.getLogger(__name__)

_CONTAINER_FIELDS = {
    "round_8gal": "borrowed_round_8gal",
    "slim_8gal": "borrowed_slim_8gal",
    "other": "borrowed_other",
}


def _resolve_care_of(care_of_id: str, user: "UserType") -> "UserType | None":
    """Resolves an optional ``care_of`` user by primary key.

    Returns ``None`` when ``care_of_id`` is empty. Raises ``ValidationError``
    when a non-empty id is supplied but no matching active user is found
    within the operator's tenant.
    """
    raw = (care_of_id or "").strip()
    if not raw:
        return None
    qs = User.objects.filter(deleted_at__isnull=True, is_active=True)
    if not user.is_superuser and user.company_id is not None:
        qs = qs.filter(company_id=user.company_id)
    care_of = qs.filter(pk=raw).first()
    if care_of is None:
        raise ValidationError("Please select a valid user for the care of field.")
    return care_of


def _to_decimal(value) -> Decimal:
    """Converts an arbitrary value to Decimal, defaulting to 0.00."""
    if value is None or value == "":
        return Decimal("0.00")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def _resolve_customer(customer_id: str, user: "UserType") -> Customer:
    """Parses a display id and returns the active customer, or raises."""
    pk = _parse_display_id(customer_id)
    if pk is None:
        raise ValidationError("Please select a customer.")
    customer = (
        Customer.objects.for_user(user)
        .filter(pk=pk, deleted_at__isnull=True)
        .first()
    )
    if customer is None:
        raise ValidationError("Please select a customer.")
    return customer


def _resolve_or_create_customer(
    customer_id: str,
    customer_name: str,
    user: "UserType",
) -> Customer:
    """Resolves an existing customer by display id, or creates a new one by name.

    This enables the insert-if-not-exists workflow in the Record Debt and
    Record Borrowed modals: the operator searches for a customer, and if
    none is found they just type the name and the system creates the
    customer on the fly with the tenant's default credit limit.

    - If ``customer_id`` is non-empty → resolves the existing customer
      (raises ``ValidationError`` if not found).
    - If ``customer_id`` is empty but ``customer_name`` is non-empty →
      creates a new customer scoped to the operator's company with the
      default credit limit from System Config.
    - If both are empty → raises ``ValidationError``.
    """
    raw_id = (customer_id or "").strip()
    raw_name = (customer_name or "").strip()

    if raw_id:
        return _resolve_customer(raw_id, user)

    if not raw_name:
        raise ValidationError("Please select a customer.")

    # Insert-if-not-exists: create a minimal customer record.  The default
    # credit limit is pulled from System Config so the operator doesn't
    # have to re-enter it — they can override it later via Edit Customer.
    customer = Customer.objects.create(
        company=getattr(user, "company", None),
        name=raw_name,
        credit_limit=get_default_credit_limit(user),
    )
    logger.info(
        "[%s] Created Customer (inline) id=%s name=%s",
        user.id,
        customer.id,
        customer.id,  # log the id, not the name (PII)
    )
    return customer


def _resolve_product(product_key: str, user: "UserType") -> Product:
    """Resolves an active product by primary key."""
    try:
        pk = int(product_key)
    except (ValueError, TypeError):
        raise ValidationError("Please select a product.")
    product = (
        Product.objects.for_user(user)
        .filter(pk=pk, deleted_at__isnull=True, deactivated_at__isnull=True)
        .first()
    )
    if product is None:
        raise ValidationError("Please select a product.")
    return product


def create_customer(
    *,
    name: str,
    contact_number: str = "",
    address: str = "",
    credit_limit="",
    performed_by: "UserType",
) -> Customer:
    """Creates a new customer record scoped to the operator's company."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("Customer name is required.")

    customer = Customer.objects.create(
        company=getattr(performed_by, "company", None),
        name=name,
        contact_number=contact_number.strip() or None,
        address=address.strip() or None,
        credit_limit=_to_decimal(credit_limit),
    )
    logger.info(
        "[%s] Created Customer id=%s company_id=%s",
        performed_by.id,
        customer.id,
        getattr(getattr(performed_by, "company", None), "id", None),
    )
    return customer


def update_customer(
    *,
    customer: Customer,
    name: str,
    contact_number: str = "",
    address: str = "",
    credit_limit="",
    performed_by: "UserType",
) -> Customer:
    """Updates an existing customer record."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("Customer name is required.")

    customer.name = name
    customer.contact_number = contact_number.strip() or None
    customer.address = address.strip() or None
    customer.credit_limit = _to_decimal(credit_limit)
    customer.full_clean()
    customer.save(
        update_fields=["name", "contact_number", "address", "credit_limit", "updated_at"]
    )
    logger.info(
        "[%s] Updated Customer id=%s",
        performed_by.id,
        customer.id,
    )
    return customer


def record_customer_debt(
    *,
    customer_id: str,
    product_key: str,
    qty_credited,
    unit_price="",
    care_of_id: str = "",
    customer_name: str = "",
    transaction_date: str = "",
    performed_by: "UserType",
) -> CreditLine:
    """Creates a credit line for a customer and increases their debt balance.

    If ``customer_id`` is provided, resolves the existing customer.  If
    only ``customer_name`` is provided (insert-if-not-exists workflow),
    creates a new customer on the fly with the default credit limit.

    ``transaction_date`` (YYYY-MM-DD string) overrides the business date
    of the credit extension — useful for recording backlog entries. It
    defaults to today and cannot be set in the future.

    Raises ``ValidationError`` if extending the credit would push the
    customer's debt balance above their configured ``credit_limit`` (a
    ``credit_limit`` of 0 means "no limit" for legacy customers).
    """
    customer = _resolve_or_create_customer(customer_id, customer_name, performed_by)
    product = _resolve_product(product_key, performed_by)
    care_of = _resolve_care_of(care_of_id, performed_by)
    tx_date = _parse_transaction_date(transaction_date)

    try:
        qty = int(qty_credited)
    except (ValueError, TypeError):
        raise ValidationError("Quantity must be a whole number.")
    if qty <= 0:
        raise ValidationError("Quantity must be greater than zero.")

    price = _to_decimal(unit_price) if unit_price else Decimal("0.00")
    if price <= 0:
        price = product.price
    total = Decimal(qty) * price

    # --- Credit limit enforcement ---------------------------------------
    # Re-read the customer row inside the transaction with a row lock so
    # concurrent debt extensions cannot both pass the limit check.  A
    # credit_limit of 0 means "no limit" (preserves legacy behaviour for
    # customers created before limits were introduced).
    with transaction.atomic():
        locked_customer = (
            Customer.objects
            .select_for_update()
            .filter(pk=customer.pk)
            .first()
        )
        if locked_customer is None:
            raise ValidationError("Please select a customer.")

        if locked_customer.credit_limit > 0:
            projected_balance = locked_customer.debt_balance + total
            if projected_balance > locked_customer.credit_limit:
                raise ValidationError(
                    f"Credit limit exceeded. The customer's limit is "
                    f"₱{locked_customer.credit_limit:,.2f} and the new "
                    f"balance would be ₱{projected_balance:,.2f}."
                )

        credit_line = CreditLine.objects.create(
            company=getattr(performed_by, "company", None),
            customer=locked_customer,
            product=product,
            remittance_rider_product=None,
            qty_credited=qty,
            qty_remaining=qty,
            unit_price_snapshot=price,
            total_credit_amount=total,
            care_of=care_of,
            transaction_date=tx_date,
        )
        # ``last_credit_at`` tracks the most recent credit extension, so a
        # backdated entry must not move it backwards — keep the greater of
        # the existing value and the new transaction date (start of day).
        tx_dt = timezone.make_aware(datetime.combine(tx_date, datetime.min.time()))
        Customer.objects.filter(pk=locked_customer.pk).update(
            debt_balance=F("debt_balance") + total,
            last_credit_at=Greatest(F("last_credit_at"), tx_dt),
        )

    customer.refresh_from_db()
    logger.info(
        "[%s] Created CreditLine id=%s customer_id=%s amount=%s care_of_id=%s",
        performed_by.id,
        credit_line.id,
        customer.id,
        total,
        getattr(care_of, "id", None),
    )
    return credit_line


def record_customer_borrowed(
    *,
    customer_id: str,
    container_key: str,
    qty_borrowed,
    care_of_id: str = "",
    customer_name: str = "",
    transaction_date: str = "",
    performed_by: "UserType",
) -> BorrowedContainer:
    """Records containers borrowed by a customer.

    Creates a :class:`BorrowedContainer` instance linked to the user
    responsible (``care_of``) and updates the aggregate counters on the
    ``Customer`` row for backward compatibility with the table/detail views.

    ``transaction_date`` (YYYY-MM-DD string) overrides the business date
    of the lending event — useful for recording backlog entries. It
    defaults to today and cannot be set in the future.

    If ``customer_id`` is provided, resolves the existing customer.  If
    only ``customer_name`` is provided (insert-if-not-exists workflow),
    creates a new customer on the fly with the default credit limit.
    """
    customer = _resolve_or_create_customer(customer_id, customer_name, performed_by)
    care_of = _resolve_care_of(care_of_id, performed_by)
    tx_date = _parse_transaction_date(transaction_date)

    if not container_key or container_key not in _CONTAINER_FIELDS:
        raise ValidationError("Please select a container type.")

    try:
        qty = int(qty_borrowed)
    except (ValueError, TypeError):
        raise ValidationError("Quantity must be a whole number.")
    if qty <= 0:
        raise ValidationError("Quantity must be greater than zero.")

    field = _CONTAINER_FIELDS[container_key]
    with transaction.atomic():
        borrowed = BorrowedContainer.objects.create(
            company=getattr(performed_by, "company", None),
            customer=customer,
            container_key=container_key,
            qty_borrowed=qty,
            qty_returned=0,
            care_of=care_of,
            recorded_by=performed_by,
            transaction_date=tx_date,
        )
        Customer.objects.filter(pk=customer.pk).update(**{field: F(field) + qty})
    customer.refresh_from_db()
    logger.info(
        "[%s] Recorded BorrowedContainer id=%s for Customer id=%s qty=%s care_of_id=%s",
        performed_by.id,
        borrowed.id,
        customer.id,
        qty,
        getattr(care_of, "id", None),
    )
    return borrowed


def delete_customer(*, customer: Customer, performed_by: "UserType") -> None:
    """Soft-deletes a customer only if they have no debt or unreturned items."""
    if customer.debt_balance > 0:
        raise ValidationError(
            "Cannot delete a customer with pending debt or unreturned containers."
        )
    if (
        customer.borrowed_round_8gal
        + customer.borrowed_slim_8gal
        + customer.borrowed_other
    ) > 0:
        raise ValidationError(
            "Cannot delete a customer with pending debt or unreturned containers."
        )

    customer.deleted_at = timezone.now()
    customer.save(update_fields=["deleted_at", "updated_at"])
    logger.info(
        "[%s] Soft-deleted Customer id=%s", performed_by.id, customer.id
    )


def _parse_int(value, field_label: str) -> int:
    """Parses a non-negative integer, raising ValidationError on bad input."""
    try:
        qty = int(value)
    except (ValueError, TypeError):
        raise ValidationError(f"{field_label} must be a whole number.")
    if qty < 0:
        raise ValidationError(f"{field_label} cannot be negative.")
    return qty


def _parse_date(value, field_label: str) -> date:
    """Parses an ISO date string, raising ValidationError on bad input."""
    raw = (value or "").strip()
    if not raw:
        raise ValidationError(f"{field_label} is required.")
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        raise ValidationError(f"{field_label} must be a valid date.")


def _parse_transaction_date(value: str) -> date:
    """Parses an optional YYYY-MM-DD transaction date for backlog entries.

    Returns ``timezone.localdate()`` when ``value`` is empty.  Rejects
    malformed strings and future dates — credit/borrowing events cannot
    have happened in the future.
    """
    if not value or not value.strip():
        return timezone.localdate()
    raw = value.strip()
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(
            "Enter a valid date (YYYY-MM-DD)."
        )
    if parsed > timezone.localdate():
        raise ValidationError(
            "Transaction date cannot be in the future."
        )
    return parsed


@transaction.atomic
def record_customer_collection(
    *,
    customer_id: str,
    performed_by: "UserType",
    returns: list[dict],
    payments: list[dict],
) -> dict:
    """Records a customer collection — container returns and/or credit payments.

    ``returns`` is a list of ``{"borrowed_id": <pk>, "qty": <int>,
    "returned_at": <str|date>}`` dicts.
    ``payments`` is a list of ``{"credit_line_id": <pk>, "qty_paid": <int>,
    "amount": <str|Decimal>, "paid_at": <str|date>}`` dicts.

    For each return, the matching ``BorrowedContainer.qty_returned`` is
    incremented, ``returned_at`` is set, and the aggregate counter on
    ``Customer`` is decremented.
    For each payment, a ``CreditPayment`` row is created with ``paid_at``,
    the ``CreditLine.qty_remaining`` is decremented, and the
    ``Customer.debt_balance`` is reduced.

    Returns a summary dict:
        {"returns_recorded": int, "payments_recorded": int, "total_collected": Decimal}

    Raises ``ValidationError`` if the customer doesn't exist, items don't
    belong to the customer, quantities are invalid, or nothing was submitted.
    """
    customer = _resolve_customer(customer_id, performed_by)
    company = getattr(performed_by, "company", None)

    # --- Parse & validate returns ------------------------------------------
    parsed_returns: list[tuple[BorrowedContainer, int, date]] = []
    for entry in returns:
        raw_id = (entry.get("borrowed_id") or "").strip()
        if not raw_id:
            continue
        try:
            borrowed_pk = int(raw_id)
        except (ValueError, TypeError):
            raise ValidationError("Invalid borrowed container reference.")

        qty = _parse_int(entry.get("qty", 0), "Return quantity")
        if qty == 0:
            continue

        returned_at = _parse_transaction_date(entry.get("returned_at", ""))

        borrowed = (
            BorrowedContainer.objects
            .filter(pk=borrowed_pk, customer=customer, company=company)
            .first()
        )
        if borrowed is None:
            raise ValidationError(
                "Borrowed container not found for this customer."
            )
        if qty > borrowed.qty_remaining:
            raise ValidationError(
                f"Cannot return {qty} containers — only "
                f"{borrowed.qty_remaining} outstanding for {borrowed.container_label}."
            )
        parsed_returns.append((borrowed, qty, returned_at))

    # --- Parse & validate payments -----------------------------------------
    parsed_payments: list[tuple[CreditLine, int, Decimal, date]] = []
    for entry in payments:
        raw_id = (entry.get("credit_line_id") or "").strip()
        if not raw_id:
            continue
        try:
            cl_pk = int(raw_id)
        except (ValueError, TypeError):
            raise ValidationError("Invalid credit line reference.")

        qty_paid = _parse_int(entry.get("qty_paid", 0), "Quantity paid")
        amount = _to_decimal(entry.get("amount", 0))
        if amount < 0:
            raise ValidationError("Payment amount cannot be negative.")
        if qty_paid == 0 and amount == 0:
            continue

        paid_at = _parse_transaction_date(entry.get("paid_at", ""))

        credit_line = (
            CreditLine.objects
            .filter(pk=cl_pk, customer=customer, company=company)
            .first()
        )
        if credit_line is None:
            raise ValidationError(
                "Credit line not found for this customer."
            )
        if qty_paid > credit_line.qty_remaining:
            raise ValidationError(
                f"Cannot pay {qty_paid} units — only "
                f"{credit_line.qty_remaining} remaining."
            )
        parsed_payments.append((credit_line, qty_paid, amount, paid_at))

    if not parsed_returns and not parsed_payments:
        raise ValidationError(
            "Nothing to record — enter a return quantity or payment amount."
        )

    # --- Re-lock rows inside the atomic block to prevent race conditions --
    # The validation above read qty_remaining / qty_returned without a lock.
    # Re-fetch with SELECT FOR UPDATE so concurrent collections cannot
    # double-spend the same credit line or borrowed container.
    locked_borrowed: dict[int, BorrowedContainer] = {}
    if parsed_returns:
        locked_borrowed = {
            b.pk: b for b in
            BorrowedContainer.objects
            .select_for_update()
            .filter(pk__in=[b.pk for b, _, _ in parsed_returns])
        }
        for borrowed, qty, _ in parsed_returns:
            current = locked_borrowed.get(borrowed.pk)
            if current is None or qty > current.qty_remaining:
                raise ValidationError(
                    "Cannot return that many containers — the outstanding "
                    "balance changed during submission. Please retry."
                )

    locked_lines: dict[int, CreditLine] = {}
    if parsed_payments:
        locked_lines = {
            cl.pk: cl for cl in
            CreditLine.objects
            .select_for_update()
            .filter(pk__in=[cl.pk for cl, _, _, _ in parsed_payments])
        }
        for credit_line, qty_paid, _, _ in parsed_payments:
            current = locked_lines.get(credit_line.pk)
            if current is None or qty_paid > current.qty_remaining:
                raise ValidationError(
                    "Cannot pay that many units — the remaining balance "
                    "changed during submission. Please retry."
                )

    # --- Apply returns -----------------------------------------------------
    returns_recorded = 0
    for borrowed, qty, returned_at in parsed_returns:
        field = _CONTAINER_FIELDS[borrowed.container_key]
        BorrowedContainer.objects.filter(pk=borrowed.pk).update(
            qty_returned=F("qty_returned") + qty,
            returned_at=returned_at,
        )
        Customer.objects.filter(pk=customer.pk).update(
            **{field: F(field) - qty}
        )
        returns_recorded += qty

    # --- Apply payments ----------------------------------------------------
    payments_recorded = 0
    total_collected = Decimal("0.00")
    for credit_line, qty_paid, amount, paid_at in parsed_payments:
        CreditPayment.objects.create(
            company=company,
            credit_line=credit_line,
            remittance=None,
            containers_paid=qty_paid,
            amount=amount,
            recorded_by=performed_by,
            paid_at=paid_at,
        )
        CreditLine.objects.filter(pk=credit_line.pk).update(
            qty_remaining=F("qty_remaining") - qty_paid
        )
        total_collected += amount
        payments_recorded += qty_paid

    if total_collected > 0:
        Customer.objects.filter(pk=customer.pk).update(
            debt_balance=F("debt_balance") - total_collected
        )

    customer.refresh_from_db()
    logger.info(
        "[%s] Recorded collection for Customer id=%s: "
        "returns=%d payments=%d collected=%s",
        performed_by.id,
        customer.id,
        returns_recorded,
        payments_recorded,
        total_collected,
    )
    return {
        "returns_recorded": returns_recorded,
        "payments_recorded": payments_recorded,
        "total_collected": total_collected,
    }


# ---------------------------------------------------------------------------
# Status transitions — the documented lifecycle
#     ACTIVE → FLAGGED → BLACKLISTED
#         ↑___________|
# is enforced here so audit logging, timestamps, and the reason field are
# always kept in sync.  Direct status mutations via the admin or shell
# bypass this and are discouraged.
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[str, set[str]] = {
    Customer.Status.ACTIVE: {Customer.Status.FLAGGED, Customer.Status.BLACKLISTED},
    Customer.Status.FLAGGED: {Customer.Status.BLACKLISTED, Customer.Status.ACTIVE},
    Customer.Status.BLACKLISTED: {Customer.Status.ACTIVE},
}


def _transition_status(
    *,
    customer: Customer,
    target: str,
    reason: str,
    performed_by: "UserType",
) -> Customer:
    """Internal helper that applies a status transition with validation."""
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A reason is required for status changes.")

    allowed = _VALID_TRANSITIONS.get(customer.status, set())
    if target not in allowed:
        raise ValidationError(
            f"Cannot move a {customer.get_status_display()} customer to "
            f"{dict(Customer.Status.choices).get(target, target)}."
        )

    now = timezone.now()
    Customer.objects.filter(pk=customer.pk).update(
        status=target,
        flagged_reason=reason if target != Customer.Status.ACTIVE else "",
        flagged_at=now if target != Customer.Status.ACTIVE else None,
        updated_at=now,
    )
    customer.refresh_from_db()
    logger.info(
        "[%s] Transitioned Customer id=%s status=%s reason_len=%d",
        performed_by.id,
        customer.id,
        target,
        len(reason),
    )
    return customer


def flag_customer(
    *, customer: Customer, reason: str, performed_by: "UserType"
) -> Customer:
    """Promotes a customer to FLAGGED status (anomaly detected)."""
    return _transition_status(
        customer=customer,
        target=Customer.Status.FLAGGED,
        reason=reason,
        performed_by=performed_by,
    )


def blacklist_customer(
    *, customer: Customer, reason: str, performed_by: "UserType"
) -> Customer:
    """Promotes a customer to BLACKLISTED status (manual ops)."""
    return _transition_status(
        customer=customer,
        target=Customer.Status.BLACKLISTED,
        reason=reason,
        performed_by=performed_by,
    )


def reset_customer_status(
    *, customer: Customer, reason: str, performed_by: "UserType"
) -> Customer:
    """Resets a customer to ACTIVE status (admin-only escape hatch)."""
    return _transition_status(
        customer=customer,
        target=Customer.Status.ACTIVE,
        reason=reason,
        performed_by=performed_by,
    )


# ---------------------------------------------------------------------------
# Ledger history edit services
# ---------------------------------------------------------------------------

from apps.remittance.models import Remittance


def _record_lock_date(record) -> date:
    """Business date used to check finalized-remittance immutability."""
    if isinstance(record, CreditPayment):
        if record.remittance_id:
            return record.remittance.date
        return record.paid_at or timezone.localtime(record.created_at).date()
    return record.transaction_date


def _verify_ledger_edit(*, record, pin: str, performed_by: "UserType") -> None:
    """Validates PIN and immutability rules before a ledger edit."""
    raw = (pin or "").strip()
    if not raw:
        raise ValidationError("PIN is required to edit this record.")

    cache_key = f"ledger_pin_attempts:{performed_by.id}"
    attempts = cache.get(cache_key, 0)
    if attempts >= 5:
        raise ValidationError(
            "Too many failed PIN attempts. Try again in 15 minutes."
        )

    if not performed_by.check_pin(raw):
        cache.set(cache_key, attempts + 1, timeout=900)
        raise ValidationError("Incorrect PIN.")

    cache.delete(cache_key)

    if is_admin(performed_by):
        return

    if (timezone.now() - record.created_at) > timedelta(hours=24):
        raise ValidationError("This record is too old to edit.")

    if (
        record.company_id
        and Remittance.objects.filter(
            company_id=record.company_id,
            date=_record_lock_date(record),
            status=Remittance.StatusChoices.FINALIZED,
        ).exists()
    ):
        raise ValidationError("This record is locked by a finalized remittance.")


def _log_ledger_edit(*, record, changes: dict, performed_by: "UserType") -> None:
    """Creates a manual LogEntry for a ledger edit."""
    content_type = ContentType.objects.get_for_model(record)
    LogEntry.objects.create(
        content_type=content_type,
        object_pk=str(record.pk),
        object_repr=str(record),
        action=LogEntry.Action.UPDATE,
        actor=performed_by,
        actor_email=performed_by.email,
        changes=changes,
        additional_data={
            "event": "ledger_edit",
            "company_id": record.company_id,
        },
    )


def _field_change(old, new):
    """Normalizes values for the audit log changes dict."""
    return [str(old), str(new)]


def _resolve_credit_line_for_edit(
    *, credit_line_id: str, customer: Customer, user: "UserType"
) -> CreditLine:
    """Resolves a CreditLine for editing, scoped to the customer and tenant."""
    try:
        pk = int(credit_line_id)
    except (ValueError, TypeError):
        raise ValidationError("Invalid credit line reference.")
    line = (
        CreditLine.objects
        .for_user(user)
        .filter(pk=pk, customer=customer)
        .select_for_update(of=("self",))
        .first()
    )
    if line is None:
        raise ValidationError("Credit line not found.")
    return line


def _resolve_credit_payment_for_edit(
    *, payment_id: str, customer: Customer, user: "UserType"
) -> CreditPayment:
    """Resolves a CreditPayment for editing, scoped to the customer and tenant."""
    try:
        pk = int(payment_id)
    except (ValueError, TypeError):
        raise ValidationError("Invalid credit payment reference.")
    payment = (
        CreditPayment.objects
        .for_user(user)
        .filter(pk=pk, credit_line__customer=customer)
        .select_for_update(of=("self",))
        .first()
    )
    if payment is None:
        raise ValidationError("Credit payment not found.")
    return payment


def _resolve_borrowed_for_edit(
    *, borrowed_id: str, customer: Customer, user: "UserType"
) -> BorrowedContainer:
    """Resolves a BorrowedContainer for editing, scoped to the customer and tenant."""
    try:
        pk = int(borrowed_id)
    except (ValueError, TypeError):
        raise ValidationError("Invalid borrowed container reference.")
    borrowed = (
        BorrowedContainer.objects
        .for_user(user)
        .filter(pk=pk, customer=customer)
        .select_for_update(of=("self",))
        .first()
    )
    if borrowed is None:
        raise ValidationError("Borrowed container not found.")
    return borrowed


def edit_credit_line(
    *,
    credit_line_id: str,
    customer: Customer,
    qty_credited,
    unit_price,
    transaction_date,
    pin: str,
    performed_by: "UserType",
) -> CreditLine:
    """Edits a CreditLine within the 24-hour editable window.

    Updates the customer's debt balance and the line's remaining quantity
    so that any payments already recorded stay consistent.
    """
    new_qty = _parse_int(qty_credited, "Quantity credited")
    new_price = _to_decimal(unit_price)
    new_transaction_date = _parse_date(transaction_date, "Transaction date")
    if new_price <= 0:
        raise ValidationError("Unit price must be greater than zero.")
    if new_qty <= 0:
        raise ValidationError("Quantity credited must be greater than zero.")

    with transaction.atomic():
        line = _resolve_credit_line_for_edit(
            credit_line_id=credit_line_id, customer=customer, user=performed_by
        )
        _verify_ledger_edit(record=line, pin=pin, performed_by=performed_by)

        old_qty = line.qty_credited
        old_price = line.unit_price_snapshot
        old_total = line.total_credit_amount
        new_total = Decimal(new_qty) * new_price

        paid = old_qty - line.qty_remaining
        new_remaining = new_qty - paid
        if new_remaining < 0:
            raise ValidationError(
                f"Quantity cannot be less than the {paid} unit(s) already paid."
            )

        delta = new_total - old_total

        old = {
            "qty_credited": line.qty_credited,
            "unit_price_snapshot": str(line.unit_price_snapshot),
            "total_credit_amount": str(line.total_credit_amount),
            "qty_remaining": line.qty_remaining,
            "transaction_date": str(line.transaction_date),
        }
        new = {
            "qty_credited": new_qty,
            "unit_price_snapshot": str(new_price),
            "total_credit_amount": str(new_total),
            "qty_remaining": new_remaining,
            "transaction_date": str(new_transaction_date),
        }

        locked_customer = (
            Customer.objects.select_for_update().filter(pk=line.customer_id).first()
        )
        if locked_customer is None:
            raise ValidationError("Customer not found.")

        projected = locked_customer.debt_balance + delta
        if projected < 0:
            raise ValidationError("Edit would result in a negative debt balance.")

        if locked_customer.credit_limit > 0 and projected > locked_customer.credit_limit:
            raise ValidationError(
                f"Credit limit exceeded. Limit is ₱{locked_customer.credit_limit:,.2f}, "
                f"projected balance would be ₱{projected:,.2f}."
            )

        CreditLine.objects.filter(pk=line.pk).update(
            qty_credited=new_qty,
            qty_remaining=new_remaining,
            unit_price_snapshot=new_price,
            total_credit_amount=new_total,
            transaction_date=new_transaction_date,
        )
        Customer.objects.filter(pk=line.customer_id).update(
            debt_balance=F("debt_balance") + delta,
        )

        line.refresh_from_db()
        _log_ledger_edit(
            record=line,
            changes={k: _field_change(old[k], new[k]) for k in old},
            performed_by=performed_by,
        )
        logger.info(
            "[%s] Edited CreditLine id=%s customer_id=%s",
            performed_by.id,
            line.id,
            line.customer_id,
        )
        return line


def edit_credit_payment(
    *,
    payment_id: str,
    customer: Customer,
    qty_paid,
    amount,
    transaction_date,
    pin: str,
    performed_by: "UserType",
) -> CreditPayment:
    """Edits a CreditPayment within the 24-hour editable window.

    Updates the parent CreditLine's remaining quantity and the customer's
    debt balance. Payments linked to a finalized remittance are blocked.
    """
    new_qty = _parse_int(qty_paid, "Quantity paid")
    new_amount = _to_decimal(amount)
    new_paid_at = _parse_date(transaction_date, "Payment date")
    if new_amount <= 0:
        raise ValidationError("Payment amount must be greater than zero.")
    if new_qty < 0:
        raise ValidationError("Quantity paid cannot be negative.")

    with transaction.atomic():
        payment = _resolve_credit_payment_for_edit(
            payment_id=payment_id, customer=customer, user=performed_by
        )
        _verify_ledger_edit(record=payment, pin=pin, performed_by=performed_by)

        old_qty = payment.containers_paid
        old_amount = payment.amount
        qty_delta = new_qty - old_qty

        old = {
            "containers_paid": payment.containers_paid,
            "amount": str(payment.amount),
            "paid_at": str(payment.paid_at) if payment.paid_at else "",
        }
        new = {
            "containers_paid": new_qty,
            "amount": str(new_amount),
            "paid_at": str(new_paid_at),
        }

        credit_line = (
            CreditLine.objects.select_for_update().filter(pk=payment.credit_line_id).first()
        )
        if credit_line is None:
            raise ValidationError("Credit line not found.")

        new_remaining = credit_line.qty_remaining - qty_delta
        if new_remaining < 0:
            raise ValidationError(
                f"Cannot pay {new_qty} unit(s) — only "
                f"{credit_line.qty_remaining + old_qty} were credited."
            )
        if new_remaining > credit_line.qty_credited:
            raise ValidationError(
                "Quantity paid cannot exceed the originally credited quantity."
            )

        locked_customer = (
            Customer.objects.select_for_update().filter(pk=credit_line.customer_id).first()
        )
        if locked_customer is None:
            raise ValidationError("Customer not found.")

        # Add back the old payment, then subtract the new payment.
        projected = locked_customer.debt_balance + old_amount - new_amount
        if projected < 0:
            raise ValidationError("Edit would result in a negative debt balance.")

        CreditPayment.objects.filter(pk=payment.pk).update(
            containers_paid=new_qty,
            amount=new_amount,
            paid_at=new_paid_at,
        )
        CreditLine.objects.filter(pk=credit_line.pk).update(
            qty_remaining=F("qty_remaining") - qty_delta,
        )
        Customer.objects.filter(pk=credit_line.customer_id).update(
            debt_balance=F("debt_balance") + old_amount - new_amount,
        )

        payment.refresh_from_db()
        _log_ledger_edit(
            record=payment,
            changes={k: _field_change(old[k], new[k]) for k in old},
            performed_by=performed_by,
        )
        logger.info(
            "[%s] Edited CreditPayment id=%s credit_line_id=%s",
            performed_by.id,
            payment.id,
            payment.credit_line_id,
        )
        return payment


def edit_borrowed_container(
    *,
    borrowed_id: str,
    customer: Customer,
    qty_borrowed,
    qty_returned,
    transaction_date,
    pin: str,
    performed_by: "UserType",
) -> BorrowedContainer:
    """Edits a BorrowedContainer within the 24-hour editable window.

    Updates the customer's aggregate borrowed counter for the container
    type so the outstanding total stays consistent.
    """
    new_borrowed = _parse_int(qty_borrowed, "Quantity borrowed")
    new_returned = _parse_int(qty_returned, "Quantity returned")
    new_transaction_date = _parse_date(transaction_date, "Transaction date")
    if new_borrowed <= 0:
        raise ValidationError("Quantity borrowed must be greater than zero.")
    if new_returned < 0:
        raise ValidationError("Quantity returned cannot be negative.")
    if new_returned > new_borrowed:
        raise ValidationError("Quantity returned cannot exceed quantity borrowed.")

    with transaction.atomic():
        borrowed = _resolve_borrowed_for_edit(
            borrowed_id=borrowed_id, customer=customer, user=performed_by
        )
        _verify_ledger_edit(record=borrowed, pin=pin, performed_by=performed_by)

        old_borrowed = borrowed.qty_borrowed
        old_returned = borrowed.qty_returned
        old_outstanding = old_borrowed - old_returned
        new_outstanding = new_borrowed - new_returned
        outstanding_delta = new_outstanding - old_outstanding

        old = {
            "qty_borrowed": borrowed.qty_borrowed,
            "qty_returned": borrowed.qty_returned,
            "transaction_date": str(borrowed.transaction_date),
        }
        new = {
            "qty_borrowed": new_borrowed,
            "qty_returned": new_returned,
            "transaction_date": str(new_transaction_date),
        }

        locked_customer = (
            Customer.objects.select_for_update().filter(pk=borrowed.customer_id).first()
        )
        if locked_customer is None:
            raise ValidationError("Customer not found.")

        field = _CONTAINER_FIELDS.get(borrowed.container_key)
        if field is None:
            raise ValidationError("Unknown container type.")

        current = getattr(locked_customer, field)
        if current + outstanding_delta < 0:
            raise ValidationError(
                "Edit would result in a negative unreturned container count."
            )

        BorrowedContainer.objects.filter(pk=borrowed.pk).update(
            qty_borrowed=new_borrowed,
            qty_returned=new_returned,
            transaction_date=new_transaction_date,
        )
        Customer.objects.filter(pk=borrowed.customer_id).update(
            **{field: F(field) + outstanding_delta}
        )

        borrowed.refresh_from_db()
        _log_ledger_edit(
            record=borrowed,
            changes={k: _field_change(old[k], new[k]) for k in old},
            performed_by=performed_by,
        )
        logger.info(
            "[%s] Edited BorrowedContainer id=%s customer_id=%s",
            performed_by.id,
            borrowed.id,
            borrowed.customer_id,
        )
        return borrowed
