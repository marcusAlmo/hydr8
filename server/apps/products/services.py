"""Write-side services for the Products & Pricing page.

All functions are keyword-only and raise ``ValidationError`` on business
rule violations.  Financial integrity is preserved by the snapshot
pattern — editing a product price or commission rate here does NOT
affect existing ``RemittanceRiderProductLine`` rows because they
snapshot ``unit_price_snapshot`` and ``commission_rate_snapshot`` at
entry time.

Layering: views call these services; services call the ORM inside
``transaction.atomic()`` blocks where multiple writes are involved.
No read logic lives here — reads go through ``selectors.py``.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import Product
from apps.users.models import DriverCommission

if TYPE_CHECKING:
    from apps.users.models import User as UserType


logger = logging.getLogger(__name__)


# --- Tenant-scoping helpers ----------------------------------------------
# Services must scope all queries by the performer's company so a staff
# user from company A cannot mutate products/commissions in company B.
# Superusers (or users without a company) bypass the filter.

def _tenant_filter(user: "UserType") -> dict:
    """Returns a filter dict for company scoping, or {} for superusers."""
    if user.is_superuser or user.company_id is None:
        return {}
    return {"company_id": user.company_id}


def _get_tenant_product(product_id: int, user: "UserType"):
    """Fetches a non-deleted product scoped to the user's tenant."""
    return (
        Product.objects
        .filter(id=product_id, deleted_at__isnull=True, **_tenant_filter(user))
        .first()
    )


def _get_tenant_driver(driver_id, user: "UserType"):
    """Fetches an active, non-deleted driver scoped to the user's tenant."""
    from apps.users.models import User
    return (
        User.objects
        .filter(id=driver_id, deleted_at__isnull=True, is_active=True,
                **_tenant_filter(user))
        .first()
    )


def _tenant_drivers(user: "UserType") -> list:
    """Returns all active drivers in the user's tenant."""
    from apps.users.models import User
    return list(
        User.objects
        .filter(role__name__iexact="driver", deleted_at__isnull=True,
                is_active=True, **_tenant_filter(user))
    )


# --- Product catalogue mutations -----------------------------------------

def create_product(
    *,
    name: str,
    variation: str | None,
    price: str | Decimal,
    category: str = "WATER",
    description: str | None = None,
    performed_by: "UserType",
) -> Product:
    """Creates a new tenant-scoped product in the catalogue.

    Raises ``ValidationError`` if the name is empty, the price is invalid,
    or an active product with the same name and variation already exists.
    """
    name = name.strip().title()
    if not name:
        raise ValidationError("Product name cannot be empty.")

    if variation is not None:
        variation = variation.strip()
        if variation:
            variation = variation.title()
        else:
            variation = None

    try:
        price_decimal = Decimal(str(price))
    except (InvalidOperation, ValueError) as e:
        raise ValidationError(f"Invalid price value: {e}") from e
    if price_decimal < 0:
        raise ValidationError("Price cannot be negative.")

    company = (
        None
        if performed_by.is_superuser or performed_by.company_id is None
        else performed_by.company
    )

    conflict = (
        Product.objects
        .filter(
            company=company,
            name=name,
            variation=variation,
            deactivated_at__isnull=True,
            deleted_at__isnull=True,
        )
        .exists()
    )
    if conflict:
        raise ValidationError(
            "A product with this name and variation already exists."
        )

    product = Product.create(
        name=name,
        variation=variation,
        price=price_decimal,
        category=category,
        description=description,
        company=company,
        is_default=False,
    )
    logger.info(
        "[%s] Created product id=%s name=%s company=%s",
        performed_by.id, product.id, product.name, product.company_id,
    )
    return product


def update_product(
    *,
    product_id: int,
    performed_by: "UserType",
    name: str | None = None,
    variation: str | None = None,
    price: str | Decimal | None = None,
) -> Product:
    """Updates an editable (non-default) product's name/variation/price.

    Raises ``ValidationError`` if the product is default-locked, not
    found, or soft-deleted.  Only non-null fields are updated — the
    view decides which fields the user changed.

    Tenant-scoped: non-superusers can only mutate products in their own
    company.
    """
    product = _get_tenant_product(product_id, performed_by)
    if product is None:
        raise ValidationError("Product not found.")
    if product.is_default:
        raise ValidationError("Default products cannot be edited.")

    update_fields: list[str] = []
    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            raise ValidationError("Product name cannot be empty.")
        product.name = cleaned
        update_fields.append("name")
    if variation is not None:
        product.variation = variation.strip()
        update_fields.append("variation")
    if price is not None:
        try:
            price_decimal = Decimal(str(price))
        except (InvalidOperation, ValueError) as e:
            raise ValidationError(f"Invalid price value: {e}") from e
        if price_decimal < 0:
            raise ValidationError("Price cannot be negative.")
        product.price = price_decimal
        update_fields.append("price")

    if not update_fields:
        raise ValidationError("No fields to update.")

    # Enforce uniqueness (active + non-deleted) before saving — the DB
    # constraint is the final guard, but we want a friendly message.
    if name is not None or variation is not None:
        conflict = (
            Product.objects
            .filter(
                company_id=product.company_id,
                name=product.name,
                variation=product.variation,
                deactivated_at__isnull=True,
                deleted_at__isnull=True,
            )
            .exclude(id=product.id)
            .exists()
        )
        if conflict:
            raise ValidationError(
                "A product with this name and variation already exists."
            )

    product.save(update_fields=update_fields + ["updated_at"])
    logger.info(
        "[%s] Updated product id=%s fields=%s",
        performed_by.id, product.id, update_fields,
    )
    return product


def activate_product(*, product_id: int, performed_by: "UserType") -> Product:
    """Re-activates a deactivated product (clears ``deactivated_at``)."""
    product = _get_tenant_product(product_id, performed_by)
    if product is None:
        raise ValidationError("Product not found.")
    if product.deactivated_at is None:
        raise ValidationError("Product is already active.")
    product.deactivated_at = None
    product.save(update_fields=["deactivated_at", "updated_at"])
    logger.info("[%s] Activated product id=%s", performed_by.id, product.id)
    return product


def deactivate_product(*, product_id: int, performed_by: "UserType") -> Product:
    """Deactivates a product (sets ``deactivated_at``).  Default products
    can be deactivated too — they just can't be edited or deleted."""
    product = _get_tenant_product(product_id, performed_by)
    if product is None:
        raise ValidationError("Product not found.")
    if product.deactivated_at is not None:
        raise ValidationError("Product is already inactive.")
    product.deactivated_at = timezone.now()
    product.save(update_fields=["deactivated_at", "updated_at"])
    logger.info("[%s] Deactivated product id=%s", performed_by.id, product.id)
    return product


def delete_product(*, product_id: int, performed_by: "UserType") -> Product:
    """Soft-deletes a non-default product (sets ``deleted_at``).

    Raises ``ValidationError`` for default products or products that are
    referenced by existing remittance lines (PROTECT FK would block a
    hard delete anyway, but we soft-delete so the audit trail is kept).
    """
    from apps.remittance.models import RemittanceRiderProductLine

    product = _get_tenant_product(product_id, performed_by)
    if product is None:
        raise ValidationError("Product not found.")
    if product.is_default:
        raise ValidationError("Default products cannot be deleted.")

    # Check for references in finalized remittance lines — if any exist,
    # we block deletion to preserve historical reporting integrity.
    has_history = (
        RemittanceRiderProductLine.objects
        .filter(product_id=product.id)
        .exists()
    )
    if has_history:
        raise ValidationError(
            "Product cannot be deleted — it has existing remittance history. "
            "Deactivate it instead."
        )

    product.deleted_at = timezone.now()
    product.save(update_fields=["deleted_at", "updated_at"])
    logger.info("[%s] Soft-deleted product id=%s", performed_by.id, product.id)
    return product


# --- Commission matrix mutations -----------------------------------------

def set_commission_rate(
    *,
    driver_id,
    product_id: int,
    rate: str | Decimal,
    performed_by: "UserType",
) -> DriverCommission:
    """Sets a single driver×product commission rate (upsert).

    Creates the ``DriverCommission`` row if it does not exist, or
    updates ``rate_per_unit`` if it does.  Tenant scope is inferred
    from the driver's company.
    """
    try:
        rate_decimal = Decimal(str(rate))
    except (InvalidOperation, ValueError) as e:
        raise ValidationError(f"Invalid rate value: {e}") from e
    if rate_decimal < 0:
        raise ValidationError("Commission rate cannot be negative.")

    from apps.users.models import User
    driver = _get_tenant_driver(driver_id, performed_by)
    if driver is None:
        raise ValidationError("Driver not found.")
    if not driver.role or driver.role.name.lower() != "driver":
        raise ValidationError("User is not a driver.")

    product = _get_tenant_product(product_id, performed_by)
    if product is None:
        raise ValidationError("Product not found.")

    obj, created = DriverCommission.objects.update_or_create(
        driver=driver,
        product=product,
        defaults={
            "rate_per_unit": rate_decimal,
            "company_id": driver.company_id,
        },
    )
    logger.info(
        "[%s] %s commission rate driver_id=%s product_id=%s rate=%s",
        performed_by.id,
        "Created" if created else "Updated",
        driver.id, product.id, rate_decimal,
    )
    return obj


def bulk_set_commission_rates(
    *,
    product_id: int,
    rate: str | Decimal,
    performed_by: "UserType",
) -> int:
    """Sets the same commission rate for ALL active drivers on a product.

    Returns the number of driver rows updated/created.  Uses
    ``update_or_create`` per driver inside a single transaction so a
    partial failure rolls back the whole batch.
    """
    try:
        rate_decimal = Decimal(str(rate))
    except (InvalidOperation, ValueError) as e:
        raise ValidationError(f"Invalid rate value: {e}") from e
    if rate_decimal < 0:
        raise ValidationError("Commission rate cannot be negative.")

    from apps.users.models import User
    product = _get_tenant_product(product_id, performed_by)
    if product is None:
        raise ValidationError("Product not found.")

    drivers = list(_tenant_drivers(performed_by))
    if not drivers:
        return 0

    with transaction.atomic():
        count = 0
        for driver in drivers:
            DriverCommission.objects.update_or_create(
                driver=driver,
                product=product,
                defaults={
                    "rate_per_unit": rate_decimal,
                    "company_id": driver.company_id,
                },
            )
            count += 1

    logger.info(
        "[%s] Bulk-set commission rate product_id=%s rate=%s drivers=%s",
        performed_by.id, product.id, rate_decimal, count,
    )
    return count


def save_commission_matrix(
    *,
    changes: dict,
    performed_by: "UserType",
) -> int:
    """Applies a batch of commission rate changes from the matrix editor.

    ``changes`` is a dict mapping ``"driver_id:product_id"`` -> rate string.
    Each entry is upserted via ``set_commission_rate`` inside a single
    transaction.  Returns the number of cells saved.

    Raises ``ValidationError`` if any single change is invalid — the
    whole batch is rolled back in that case (atomicity over partial
    success).
    """
    if not changes:
        raise ValidationError("No changes to save.")

    with transaction.atomic():
        count = 0
        for key, rate in changes.items():
            try:
                driver_id_str, product_id_str = key.split(":", 1)
                product_id = int(product_id_str)
            except (ValueError, AttributeError) as e:
                raise ValidationError(f"Invalid change key '{key}': {e}") from e
            set_commission_rate(
                driver_id=driver_id_str,
                product_id=product_id,
                rate=rate,
                performed_by=performed_by,
            )
            count += 1

    logger.info(
        "[%s] Saved commission matrix changes count=%s",
        performed_by.id, count,
    )
    return count
