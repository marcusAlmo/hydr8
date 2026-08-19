"""Tests for the data-integrity constraints and status transitions added
in the customers-domain hardening pass.

Covers:
  - Database CheckConstraints (debt_balance, qty_remaining, qty_returned)
  - Unique active customer name per company
  - Credit limit enforcement in ``record_customer_debt``
  - Status transition service methods (flag / blacklist / reset)
  - Soft-delete protection signal
  - PII-safe ``__str__`` representations
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Product
from apps.customers.models import (
    BorrowedContainer,
    CreditLine,
    CreditPayment,
    Customer,
)
from apps.customers.services import (
    blacklist_customer,
    flag_customer,
    record_customer_borrowed,
    record_customer_collection,
    record_customer_debt,
    reset_customer_status,
)
from apps.core.models import Company
from apps.users.models import Role, User


def _display_id(customer: Customer) -> str:
    return f"HY-{customer.pk:04d}"


def _make_staff_user(**kwargs) -> User:
    """Creates a test user with the canonical Staff back-office role."""
    staff_role, _ = Role.objects.get_or_create(name="Staff", company=None)
    return User.objects.create_user(role=staff_role, **kwargs)


class CreditLimitEnforcementTests(TestCase):
    """``record_customer_debt`` must refuse to exceed ``credit_limit``."""

    def setUp(self):
        self.staff = _make_staff_user(
            username="limit_staff", password="securepassword123"
        )
        self.customer = Customer.objects.create(
            name="Limit Test Store",
            credit_limit=Decimal("100.00"),
        )
        self.product = Product.objects.create(
            name="Alkaline", variation="Round", price=Decimal("40.00")
        )

    def test_debt_within_limit_succeeds(self):
        """A debt that stays under the limit is recorded normally."""
        line = record_customer_debt(
            customer_id=_display_id(self.customer),
            product_key=str(self.product.pk),
            qty_credited=2,
            unit_price="40.00",
            performed_by=self.staff,
        )
        self.assertEqual(line.qty_credited, 2)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.debt_balance, Decimal("80.00"))

    def test_debt_exceeding_limit_raises(self):
        """A debt that would push the balance over the limit is rejected."""
        with self.assertRaises(ValidationError) as ctx:
            record_customer_debt(
                customer_id=_display_id(self.customer),
                product_key=str(self.product.pk),
                qty_credited=3,
                unit_price="40.00",
                performed_by=self.staff,
            )
        self.assertIn("Credit limit exceeded", str(ctx.exception))

    def test_zero_credit_limit_means_no_limit(self):
        """A credit_limit of 0 preserves legacy 'no limit' behaviour."""
        self.customer.credit_limit = Decimal("0.00")
        self.customer.save(update_fields=["credit_limit"])
        # Should not raise even for a large amount.
        record_customer_debt(
            customer_id=_display_id(self.customer),
            product_key=str(self.product.pk),
            qty_credited=100,
            unit_price="40.00",
            performed_by=self.staff,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.debt_balance, Decimal("4000.00"))

    def test_debt_at_exactly_the_limit_is_allowed(self):
        """A debt that lands exactly on the limit is permitted."""
        record_customer_debt(
            customer_id=_display_id(self.customer),
            product_key=str(self.product.pk),
            qty_credited=2,
            unit_price="50.00",
            performed_by=self.staff,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.debt_balance, Decimal("100.00"))


class CustomerStatusTransitionTests(TestCase):
    """Status transitions go through the service layer with validation."""

    def setUp(self):
        self.staff = _make_staff_user(
            username="status_staff", password="securepassword123"
        )
        self.customer = Customer.objects.create(name="Status Test Store")

    def test_flag_active_customer(self):
        """ACTIVE → FLAGGED is allowed and stamps flagged_at."""
        flag_customer(
            customer=self.customer,
            reason="3 overdue cycles",
            performed_by=self.staff,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, Customer.Status.FLAGGED)
        self.assertEqual(self.customer.flagged_reason, "3 overdue cycles")
        self.assertIsNotNone(self.customer.flagged_at)

    def test_blacklist_flagged_customer(self):
        """FLAGGED → BLACKLISTED is allowed."""
        self.customer.status = Customer.Status.FLAGGED
        self.customer.flagged_reason = "anomaly"
        self.customer.save()
        blacklist_customer(
            customer=self.customer,
            reason="confirmed fraud",
            performed_by=self.staff,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, Customer.Status.BLACKLISTED)

    def test_reset_to_active_clears_flagged_fields(self):
        """Resetting to ACTIVE clears the reason and timestamp."""
        self.customer.status = Customer.Status.BLACKLISTED
        self.customer.flagged_reason = "fraud"
        self.customer.flagged_at = timezone.now()
        self.customer.save()
        reset_customer_status(
            customer=self.customer,
            reason="cleared by admin",
            performed_by=self.staff,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, Customer.Status.ACTIVE)
        self.assertEqual(self.customer.flagged_reason, "")
        self.assertIsNone(self.customer.flagged_at)

    def test_invalid_transition_raises(self):
        """ACTIVE → ACTIVE is not a valid transition."""
        with self.assertRaises(ValidationError):
            flag_customer(
                customer=self.customer,
                reason="x",
                performed_by=self.staff,
            ) if False else reset_customer_status(
                customer=self.customer,
                reason="already active",
                performed_by=self.staff,
            )

    def test_blacklist_active_customer_skips_flagged(self):
        """ACTIVE → BLACKLISTED is allowed (skips FLAGGED)."""
        blacklist_customer(
            customer=self.customer,
            reason="severe case",
            performed_by=self.staff,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, Customer.Status.BLACKLISTED)

    def test_missing_reason_raises(self):
        """A status change without a reason is rejected."""
        with self.assertRaises(ValidationError):
            flag_customer(
                customer=self.customer, reason="", performed_by=self.staff
            )


class SoftDeleteSignalTests(TestCase):
    """The pre_save signal blocks unsafe soft-deletion."""

    def setUp(self):
        self.staff = _make_staff_user(
            username="delete_staff", password="securepassword123"
        )
        self.product = Product.objects.create(
            name="Alkaline", variation="Round", price=Decimal("40.00")
        )

    def test_soft_delete_blocked_when_debt_exists(self):
        """A customer with debt cannot be soft-deleted via ORM."""
        customer = Customer.objects.create(name="Debtor Store")
        record_customer_debt(
            customer_id=_display_id(customer),
            product_key=str(self.product.pk),
            qty_credited=1,
            unit_price="40.00",
            performed_by=self.staff,
        )
        customer.deleted_at = timezone.now()
        with self.assertRaises(ValidationError):
            customer.save()

    def test_soft_delete_blocked_when_containers_out(self):
        """A customer with unreturned containers cannot be soft-deleted."""
        customer = Customer.objects.create(name="Borrower Store")
        record_customer_borrowed(
            customer_id=_display_id(customer),
            container_key="round_8gal",
            qty_borrowed=2,
            performed_by=self.staff,
        )
        customer.deleted_at = timezone.now()
        with self.assertRaises(ValidationError):
            customer.save()

    def test_soft_delete_allowed_when_clean(self):
        """A customer with no debt/containers can be soft-deleted."""
        customer = Customer.objects.create(name="Clean Store")
        customer.deleted_at = timezone.now()
        customer.save()  # should not raise
        customer.refresh_from_db()
        self.assertIsNotNone(customer.deleted_at)


class UniqueCustomerNameTests(TestCase):
    """The unique-active-name-per-company constraint."""

    def setUp(self):
        self.company = Company.objects.create(name="Test Co")

    def test_duplicate_active_name_raises(self):
        """Two active customers with the same name in one company clash."""
        Customer.objects.create(name="Dupe Store", company=self.company)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Customer.objects.create(name="Dupe Store", company=self.company)

    def test_soft_deleted_name_can_be_reused(self):
        """A soft-deleted customer's name can be reused."""
        first = Customer.objects.create(name="Recyclable Store", company=self.company)
        first.deleted_at = timezone.now()
        first.save()
        # Should not raise — the soft-deleted row is excluded by the
        # partial unique constraint.
        second = Customer.objects.create(name="Recyclable Store", company=self.company)
        self.assertIsNotNone(second.pk)

    def test_same_name_in_different_companies_ok(self):
        """The same name in two different companies is fine."""
        other = Company.objects.create(name="Other Co")
        Customer.objects.create(name="Shared Name", company=self.company)
        Customer.objects.create(name="Shared Name", company=other)  # no error


class PIIStringRepresentationTests(TestCase):
    """``__str__`` must not leak customer names (RA 10173)."""

    def test_credit_line_str_hides_customer_name(self):
        customer = Customer(name="Secret Customer")
        product = Product(name="Water 5G")
        line = CreditLine(customer=customer, product=product, qty_remaining=3, pk=11)
        rendered = str(line)
        self.assertNotIn("Secret Customer", rendered)
        self.assertIn("CL-11", rendered)

    def test_borrowed_container_str_hides_customer_name(self):
        customer = Customer(name="Secret Borrower")
        borrowed = BorrowedContainer(
            customer=customer,
            container_key="round_8gal",
            qty_borrowed=5,
            qty_returned=1,
            pk=22,
        )
        rendered = str(borrowed)
        self.assertNotIn("Secret Borrower", rendered)
        self.assertIn("BC-22", rendered)

    def test_credit_payment_str_hides_customer_name(self):
        customer = Customer(name="Secret Payer")
        product = Product(name="Water 5G")
        line = CreditLine(customer=customer, product=product, qty_remaining=2)
        payment = CreditPayment(credit_line=line, amount=Decimal("80.00"), pk=33)
        rendered = str(payment)
        self.assertNotIn("Secret Payer", rendered)
        self.assertIn("CP-33", rendered)


class DatabaseConstraintTests(TestCase):
    """Verify the DB-level CheckConstraints reject invalid rows."""

    def test_negative_debt_balance_rejected(self):
        """The DB rejects a negative debt_balance."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Customer.objects.create(
                    name="Negative Debt", debt_balance=Decimal("-1.00")
                )

    def test_negative_credit_limit_rejected(self):
        """The DB rejects a negative credit_limit."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Customer.objects.create(
                    name="Negative Limit", credit_limit=Decimal("-50.00")
                )

    def test_negative_borrowed_counter_rejected(self):
        """The DB rejects a negative borrowed_* counter."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Customer.objects.create(
                    name="Negative Borrowed", borrowed_round_8gal=-1
                )

    def test_credit_line_qty_remaining_above_credited_rejected(self):
        """qty_remaining cannot exceed qty_credited at the DB level."""
        customer = Customer.objects.create(name="CL Constraint Store")
        product = Product.objects.create(name="Water", price=Decimal("10.00"))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CreditLine.objects.create(
                    customer=customer,
                    product=product,
                    qty_credited=5,
                    qty_remaining=6,
                    unit_price_snapshot=Decimal("10.00"),
                    total_credit_amount=Decimal("50.00"),
                )

    def test_borrowed_qty_returned_above_borrowed_rejected(self):
        """qty_returned cannot exceed qty_borrowed at the DB level."""
        customer = Customer.objects.create(name="BC Constraint Store")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BorrowedContainer.objects.create(
                    customer=customer,
                    container_key="round_8gal",
                    qty_borrowed=3,
                    qty_returned=4,
                )

    def test_negative_credit_payment_amount_rejected(self):
        """A negative payment amount is rejected at the DB level."""
        customer = Customer.objects.create(name="CP Constraint Store")
        product = Product.objects.create(name="Water", price=Decimal("10.00"))
        line = CreditLine.objects.create(
            customer=customer,
            product=product,
            qty_credited=2,
            qty_remaining=2,
            unit_price_snapshot=Decimal("10.00"),
            total_credit_amount=Decimal("20.00"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CreditPayment.objects.create(
                    credit_line=line,
                    containers_paid=1,
                    amount=Decimal("-5.00"),
                )
