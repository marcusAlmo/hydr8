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


@transaction.atomic
def create_and_finalize_remittance(
    *,
    performed_by: "UserType",
    riders_data: list[dict],
    expenses_data: list[dict],
    manual_offering,
    tithe_rate,
    remittance_date=None,
) -> Remittance:
    """Creates a finalized daily remittance from the client payload.

    Raises ``ValidationError`` if the date is already finalized, a rider or
    product cannot be resolved, or any financial total is negative.
    """
    company = getattr(performed_by, "company", None)
    remittance_date = remittance_date or date.today()

    if Remittance.objects.filter(company=company, date=remittance_date).exists():
        raise ValidationError(
            f"A remittance for {remittance_date} has already been finalized."
        )

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
    remittance = Remittance.objects.create(
        date=remittance_date,
        company=company,
        created_by=performed_by,
        status=Remittance.StatusChoices.FINALIZED,
        finalized_by=performed_by,
        finalized_at=timezone.now(),
        tithe_rate_snapshot=_to_decimal(tithe_rate),
        offering_amount=_to_decimal(manual_offering),
    )

    total_sales = Decimal("0.00")
    total_credit_sales = Decimal("0.00")
    total_commission = Decimal("0.00")
    total_expenses = Decimal("0.00")
    total_borrowed_items = 0

    active_riders = _active_riders_qs(performed_by)

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

    net_profit = total_sales - total_expenses - total_commission
    tithe_amount = net_profit * remittance.tithe_rate_snapshot

    remittance.total_sales = total_sales
    remittance.total_credit_sales = total_credit_sales
    remittance.total_commission = total_commission
    remittance.total_expenses = total_expenses
    remittance.total_borrowed_items = total_borrowed_items
    remittance.net_profit = net_profit
    remittance.tithe_amount = tithe_amount
    remittance.save(
        update_fields=[
            "total_sales",
            "total_credit_sales",
            "total_commission",
            "total_expenses",
            "total_borrowed_items",
            "net_profit",
            "tithe_amount",
            "updated_at",
        ]
    )

    logger.info(
        "[%s] Created Remittance id=%s company_id=%s total_sales=%s net_profit=%s",
        performed_by.id,
        remittance.id,
        getattr(company, "id", None),
        total_sales,
        net_profit,
    )
    return remittance
