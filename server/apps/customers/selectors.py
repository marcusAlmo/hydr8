"""Read-side selectors for the Customers pages.

Selectors return *raw data* — querysets, model instances, aggregates, and
simple values.  They never shape template-ready dicts; that responsibility
lives in :mod:`apps.customers.presentation`.

Views (and presentation functions) call these — they never hit the ORM
directly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum
from django.utils import timezone

from apps.core.models import Product
from apps.core.selectors_settings import get_overdue_threshold_days
from apps.remittance.models import Remittance
from apps.users.models import User
from apps.users.permissions import is_admin

from .models import BorrowedContainer, Customer, CreditLine, CreditPayment

if TYPE_CHECKING:
    from apps.users.models import User as UserType

logger = logging.getLogger(__name__)

_CUSTOMER_DISPLAY_PREFIX = "HY"

# ---------------------------------------------------------------------------
# Sort mapping for the customer table HTMX partial.
# ---------------------------------------------------------------------------
SORT_FIELD_MAP: dict[str, str] = {
    "name": "name",
    "debt_balance": "debt_balance_raw",
    "borrowed_total": "borrowed_total",
    "payable_amount": "payable_amount_raw",
    "last_credit": "last_credit_days",
}
DEFAULT_SORT = "name"
DEFAULT_DIR = "asc"
PER_PAGE = 25

# Maps sort field names to actual DB column/annotation names for DB-side sorting.
# "last_credit" maps to "last_credit_at" with inverted direction (more recent = fewer days).
_DB_SORT_MAP: dict[str, str] = {
    "name": "name",
    "debt_balance": "debt_balance",
    "borrowed_total": "borrowed_total",  # annotated
    "payable_amount": "debt_balance",     # same value as debt_balance
    "last_credit": "last_credit_at",      # direction inverted below
}


def _parse_display_id(customer_id: str) -> int | None:
    """Parses a display id (``HY-XXXX`` or plain int) back to a primary key."""
    raw = customer_id
    if raw.startswith(_CUSTOMER_DISPLAY_PREFIX + "-"):
        raw = raw.split("-", 1)[1]
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def get_customer_by_display_id(user: "UserType", customer_id: str) -> Customer | None:
    """Resolves a customer from a display id such as ``HY-0001``."""
    pk = _parse_display_id(customer_id)
    if pk is None:
        return None
    return (
        Customer.objects.for_user(user)
        .filter(pk=pk, deleted_at__isnull=True)
        .first()
    )


def _last_payment_dt(customer: Customer) -> datetime | None:
    payment = (
        CreditPayment.objects.filter(credit_line__customer=customer)
        .order_by("-created_at")
        .first()
    )
    return payment.created_at if payment else None


# ---------------------------------------------------------------------------
# Raw-data selectors consumed by presentation functions.
# ---------------------------------------------------------------------------

def customer_filter_counts(user: "UserType") -> dict[str, int]:
    """Returns raw counts for each customer-table filter bucket."""
    base = Customer.objects.for_user(user).filter(deleted_at__isnull=True)
    return {
        "all": base.count(),
        "has_debt": base.filter(debt_balance__gt=0).count(),
        "has_borrowed": base.filter(
            Q(borrowed_round_8gal__gt=0)
            | Q(borrowed_slim_8gal__gt=0)
            | Q(borrowed_other__gt=0)
        ).count(),
        "anomalous": base.filter(
            status__in=(Customer.Status.FLAGGED, Customer.Status.BLACKLISTED)
        ).count(),
    }


def customer_stats_raw(user: "UserType") -> dict:
    """Returns raw aggregate values for the Summary tab stat cards.

    Includes both customer-directory metrics (total customers, unreturned
    containers) and debt-management metrics (total outstanding, overdue
    7+ days, avg days overdue) — the latter were migrated from the now-
    retired Debt Management tab so all KPIs are visible in one place.
    """
    threshold = get_overdue_threshold_days(user)
    base = Customer.objects.for_user(user).filter(deleted_at__isnull=True)
    total = base.count()

    # Combine the debtor_count + total_debt queries into a single
    # aggregate pass over the debtors subset.
    debt_stats = base.filter(debt_balance__gt=0).aggregate(
        debtor_count=Count("id"),
        total_debt=Sum("debt_balance"),
    )
    debtor_count = debt_stats["debtor_count"] or 0
    total_debt = debt_stats["total_debt"] or Decimal("0.00")

    borrowed_total = (
        base.aggregate(
            total=Sum(
                F("borrowed_round_8gal")
                + F("borrowed_slim_8gal")
                + F("borrowed_other")
            )
        )["total"]
        or 0
    )
    borrowed_count = base.filter(
        Q(borrowed_round_8gal__gt=0)
        | Q(borrowed_slim_8gal__gt=0)
        | Q(borrowed_other__gt=0)
    ).count()

    # Debt-management metrics (migrated from the retired Debt Management tab).
    # Compute overdue_count and avg_days_overdue DB-side so we don't load
    # every debtor row into memory.  Customers with no last_credit_at are
    # treated as "Never credited" — they are debtors but never overdue
    # (no clock has started).
    threshold_date = timezone.now() - timedelta(days=threshold)
    overdue_count = base.filter(
        debt_balance__gt=0,
        last_credit_at__lt=threshold_date,
    ).count()

    # Average days overdue across active debtors.  We still need a single
    # pass over debtors for the average, but we limit to only the columns
    # we need and let the DB do the date math where possible.
    avg_days = 0
    if debtor_count:
        now = timezone.now()

        def _days_since(dt) -> int:
            if not dt:
                return 9999
            if dt > now:
                return 0
            return (now - dt).days

        debtors_list = list(
            base.filter(debt_balance__gt=0).only("last_credit_at")
        )
        avg_days = round(
            sum(_days_since(c.last_credit_at) for c in debtors_list) / debtor_count
        )

    return {
        "threshold": threshold,
        "total": total,
        "debtor_count": debtor_count,
        "total_debt": total_debt,
        "borrowed_total": borrowed_total,
        "borrowed_count": borrowed_count,
        "overdue_count": overdue_count,
        "avg_days": avg_days,
    }


def top_payers(user: "UserType") -> list[Customer]:
    """Top 5 customers by total payment amount, with payment annotations."""
    return list(
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True, credit_lines__payments__isnull=False)
        .annotate(
            total_paid=Sum("credit_lines__payments__amount"),
            payment_count=Count("credit_lines__payments", distinct=True),
        )
        .order_by("-total_paid")[:5]
    )


def payer_count(user: "UserType") -> int:
    """Count of customers with at least one recorded payment."""
    return (
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True, credit_lines__payments__isnull=False)
        .distinct()
        .count()
    )


def customer_table_page(
    user: "UserType",
    sort_field: str = DEFAULT_SORT,
    direction: str = DEFAULT_DIR,
    query: str = "",
    page: int = 1,
) -> dict:
    """Returns raw paginated customer-table data.

    The returned dict carries the validated sort state and the Django
    ``Page`` object; presentation functions shape the rows/pagination.
    """
    next_dir = "desc" if direction == "asc" else "asc"

    qs = Customer.objects.for_user(user).filter(deleted_at__isnull=True)

    # Apply search filter
    query = (query or "").strip()
    if query:
        qs = qs.filter(name__icontains=query)

    # Annotate borrowed_total for sorting
    qs = qs.annotate(
        borrowed_total=F("borrowed_round_8gal") + F("borrowed_slim_8gal") + F("borrowed_other")
    )

    # DB-side sorting
    db_sort = _DB_SORT_MAP.get(sort_field, _DB_SORT_MAP[DEFAULT_SORT])
    if sort_field == "last_credit":
        # Invert direction: last_credit_days asc = last_credit_at desc
        if direction == "asc":
            qs = qs.order_by(F("last_credit_at").desc(nulls_last=True))
        else:
            qs = qs.order_by(F("last_credit_at").asc(nulls_last=True))
    else:
        if direction == "desc":
            db_sort = f"-{db_sort}"
        qs = qs.order_by(db_sort)

    # Real pagination
    paginator = Paginator(qs, PER_PAGE)
    page_obj = paginator.get_page(page)

    return {
        "page_obj": page_obj,
        "query": query,
        "sort_field": sort_field,
        "direction": direction,
        "next_dir": next_dir,
    }


def customer_detail_raw(customer: Customer, user: "UserType | None" = None) -> dict:
    """Returns raw aggregates for the detail modal.

    The configurable overdue threshold is read from SystemConfig and
    returned so presentation can compute the ``is_overdue`` display flag.
    """
    return {
        "threshold": get_overdue_threshold_days(user) if user is not None else 7,
        "last_payment_dt": _last_payment_dt(customer),
        "total_credits": customer.credit_lines.count(),
    }


def customer_collect_raw(customer: Customer) -> tuple:
    """Returns the open credit lines and borrowed containers (querysets).

    Credit lines are grouped by the rider who delivered them (via
    ``remittance_rider_product``); borrowed containers are grouped by
    their ``care_of`` user so responsibility is visible per item.
    """
    open_lines = (
        CreditLine.objects.filter(customer=customer, qty_remaining__gt=0)
        .select_related(
            "product",
            "care_of",
            "care_of__role",
            "remittance_rider_product__remittance_rider__rider",
        )
        .order_by("product__name")
    )

    open_borrowed = (
        BorrowedContainer.objects.filter(customer=customer, qty_returned__lt=F("qty_borrowed"))
        .select_related("care_of", "care_of__role")
        .order_by("-transaction_date", "-created_at")
    )

    return open_lines, open_borrowed


def care_of_users_qs(user: "UserType") -> list[User]:
    """Active users in the operator's tenant, for the ``care of`` dropdown.

    Includes admins, staff, and drivers — anyone who could be responsible
    for lending containers or extending credit to a customer.  Returns
    raw ``User`` instances; presentation builds the label dicts.
    """
    qs = User.objects.filter(deleted_at__isnull=True, is_active=True).select_related(
        "role"
    )
    if not user.is_superuser and user.company_id is not None:
        qs = qs.filter(company_id=user.company_id)
    qs = qs.order_by("first_name", "last_name", "username")
    return list(qs)


def record_debt_raw(user: "UserType") -> tuple:
    """Returns raw customer/product/user lists for the record-debt modal."""
    customers = (
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True)
        .order_by("name")
    )
    products = (
        Product.objects.for_user(user)
        .filter(deleted_at__isnull=True, deactivated_at__isnull=True)
        .order_by("name", "variation")
    )
    return customers, products, care_of_users_qs(user)


def record_borrowed_raw(user: "UserType") -> tuple:
    """Returns raw customer/user lists for the record-borrowed modal."""
    customers = (
        Customer.objects.for_user(user)
        .filter(deleted_at__isnull=True)
        .order_by("name")
    )
    return customers, care_of_users_qs(user)


def customer_history_raw(customer: Customer) -> tuple:
    """Returns the raw ledger querysets for a customer's unified history."""
    credit_lines = (
        CreditLine.objects.filter(customer=customer)
        .select_related("product", "care_of", "company")
        .order_by("-created_at")
    )
    payments = (
        CreditPayment.objects.filter(credit_line__customer=customer)
        .select_related("credit_line__product", "credit_line__care_of", "recorded_by", "company", "remittance")
        .order_by("-created_at")
    )
    borrowed = (
        BorrowedContainer.objects.filter(customer=customer)
        .select_related("care_of", "recorded_by", "company")
        .order_by("-created_at")
    )
    return credit_lines, payments, borrowed


# ---------------------------------------------------------------------------
# Business rules (edit/delete permission) — consumed by presentation.
# ---------------------------------------------------------------------------

def _history_entry_editable(record, user) -> tuple[bool, str]:
    """Returns (is_editable, reason) for a ledger record.

    Admins may edit all fields at any time. Staff may edit for 24 hours
    after creation unless the business date has already been locked by a
    finalized remittance.
    """
    if is_admin(user):
        return True, ""

    now = timezone.now()
    if (now - record.created_at) > timedelta(hours=24):
        return False, "Older than 24 hours"

    company = record.company
    if record._meta.model_name == "creditpayment":
        remittance = record.remittance
        if remittance is not None:
            check_date = remittance.date
        else:
            check_date = record.paid_at or timezone.localtime(record.created_at).date()
    else:
        check_date = record.transaction_date

    if (
        company is not None
        and Remittance.objects.filter(
            company=company,
            date=check_date,
            status=Remittance.StatusChoices.FINALIZED,
        ).exists()
    ):
        return False, "Remittance finalized for this date"

    return True, ""


def _history_entry_deletable(record, user) -> tuple[bool, str]:
    """Returns (is_deletable, reason) for a ledger record.

    Deletion is admin-only.  Additionally, records linked to a remittance
    (directly, or via child payments) cannot be deleted because the
    ``CreditPayment.remittance`` FK uses ``on_delete=PROTECT``.
    """
    if not is_admin(user):
        return False, "Admin only"

    if record._meta.model_name == "creditpayment":
        if record.remittance_id is not None:
            return False, "Linked to a remittance"
        return True, ""

    if record._meta.model_name == "creditline":
        if record.payments.filter(remittance__isnull=False).exists():
            return False, "Has payments linked to a remittance"
        return True, ""

    # BorrowedContainer — no remittance linkage, always deletable for admin.
    return True, ""
