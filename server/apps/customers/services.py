"""Write-side services for the Customers app.

All customer mutations (add, debt, borrowed, delete) live here.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.models import Product

from .models import Customer, CreditLine
from .selectors import _parse_display_id

if TYPE_CHECKING:
    from apps.users.models import User as UserType

logger = logging.getLogger(__name__)

_CONTAINER_FIELDS = {
    "round_8gal": "borrowed_round_8gal",
    "slim_8gal": "borrowed_slim_8gal",
    "other": "borrowed_other",
}


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
    performed_by: "UserType",
) -> CreditLine:
    """Creates a credit line for a customer and increases their debt balance."""
    customer = _resolve_customer(customer_id, performed_by)
    product = _resolve_product(product_key, performed_by)

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

    with transaction.atomic():
        credit_line = CreditLine.objects.create(
            company=getattr(performed_by, "company", None),
            customer=customer,
            product=product,
            remittance_rider_product=None,
            qty_credited=qty,
            qty_remaining=qty,
            unit_price_snapshot=price,
            total_credit_amount=total,
        )
        Customer.objects.filter(pk=customer.pk).update(
            debt_balance=F("debt_balance") + total,
            last_credit_at=timezone.now(),
        )

    customer.refresh_from_db()
    logger.info(
        "[%s] Created CreditLine id=%s customer_id=%s amount=%s",
        performed_by.id,
        credit_line.id,
        customer.id,
        total,
    )
    return credit_line


def record_customer_borrowed(
    *,
    customer_id: str,
    container_key: str,
    qty_borrowed,
    performed_by: "UserType",
) -> Customer:
    """Records containers borrowed by a customer, updating their counts."""
    customer = _resolve_customer(customer_id, performed_by)

    if not container_key or container_key not in _CONTAINER_FIELDS:
        raise ValidationError("Please select a container type.")

    try:
        qty = int(qty_borrowed)
    except (ValueError, TypeError):
        raise ValidationError("Quantity must be a whole number.")
    if qty <= 0:
        raise ValidationError("Quantity must be greater than zero.")

    field = _CONTAINER_FIELDS[container_key]
    Customer.objects.filter(pk=customer.pk).update(**{field: F(field) + qty})
    customer.refresh_from_db()
    logger.info(
        "[%s] Recorded %s borrowed container(s) for Customer id=%s",
        performed_by.id,
        qty,
        customer.id,
    )
    return customer


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

    Customer.objects.for_user(performed_by).filter(pk=customer.pk).update(
        deleted_at=timezone.now()
    )
    logger.info(
        "[%s] Soft-deleted Customer id=%s", performed_by.id, customer.id
    )
