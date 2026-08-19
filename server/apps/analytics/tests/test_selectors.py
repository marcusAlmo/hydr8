"""Tests for the analytics dashboard selectors.

Selectors return raw data — Decimals, model instances, lists of dicts
with unformatted DB values. Presentation-layer formatting (currency
strings, CSS classes, card shapes) is tested in test_presentation.py.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Product
from apps.customers.models import CreditLine, Customer
from apps.remittance.models import Remittance
from apps.users.models import User

from apps.analytics import selectors


class TodaySalesTests(TestCase):
    """Tests for get_today_sales."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="sales_user", password="securepassword123"
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_returns_sales_when_remittance_exists(self):
        """Returns total_sales when a remittance exists for today."""
        today = timezone.localdate()
        Remittance.objects.create(
            date=today,
            created_by=self.user,
            total_sales=Decimal("500.00"),
        )
        result = selectors.get_today_sales(self.user)
        self.assertEqual(result, Decimal("500.00"))

    def test_returns_zero_when_no_remittance(self):
        """Returns Decimal('0.00') when no remittance exists for today."""
        result = selectors.get_today_sales(self.user)
        self.assertEqual(result, Decimal("0.00"))


class YesterdaySalesTests(TestCase):
    """Tests for get_yesterday_sales."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="yesterday_user", password="securepassword123"
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_returns_yesterday_sales(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        Remittance.objects.create(
            date=yesterday,
            created_by=self.user,
            total_sales=Decimal("500.00"),
        )
        result = selectors.get_yesterday_sales(self.user)
        self.assertEqual(result, Decimal("500.00"))

    def test_returns_zero_when_no_remittance(self):
        result = selectors.get_yesterday_sales(self.user)
        self.assertEqual(result, Decimal("0.00"))


class OutstandingDebtTests(TestCase):
    """Tests for get_outstanding_debt."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="debt_user", password="securepassword123"
        )
        self.product = Product.objects.create(
            name="Water", variation="1L", price=Decimal("40.00")
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_sums_debt_across_customers(self):
        """Sums debt_balance across all non-deleted customers."""
        Customer.objects.create(name="C1", debt_balance=Decimal("100.00"))
        Customer.objects.create(name="C2", debt_balance=Decimal("200.00"))
        result = selectors.get_outstanding_debt(self.user)
        self.assertEqual(result, Decimal("300.00"))

    def test_returns_zero_when_no_customers(self):
        """Returns Decimal('0.00') when no customers exist."""
        result = selectors.get_outstanding_debt(self.user)
        self.assertEqual(result, Decimal("0.00"))

    def test_excludes_deleted_customers(self):
        """Deleted customers are excluded from the sum."""
        Customer.objects.create(
            name="Deleted",
            debt_balance=Decimal("500.00"),
            deleted_at=timezone.now(),
        )
        result = selectors.get_outstanding_debt(self.user)
        self.assertEqual(result, Decimal("0.00"))


class UnreturnedContainerCountsTests(TestCase):
    """Tests for get_unreturned_container_counts."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="containers_user", password="securepassword123"
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_sums_containers_across_customers(self):
        """Sums borrowed containers across all customers."""
        Customer.objects.create(
            name="C1",
            borrowed_round_8gal=3,
            borrowed_slim_8gal=2,
            borrowed_other=1,
        )
        result = selectors.get_unreturned_container_counts(self.user)
        self.assertEqual(result["round"], 3)
        self.assertEqual(result["slim"], 2)
        self.assertEqual(result["other"], 1)

    def test_returns_zero_when_no_customers(self):
        """Returns all zeros when no customers exist."""
        result = selectors.get_unreturned_container_counts(self.user)
        self.assertEqual(result["round"], 0)
        self.assertEqual(result["slim"], 0)
        self.assertEqual(result["other"], 0)


class TodayRemittanceSelectorTests(TestCase):
    """Tests for get_today_remittance (returns Remittance or None)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="banner_user", password="securepassword123"
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_returns_none_when_no_remittance_today(self):
        """Returns None when no remittance exists for today."""
        result = selectors.get_today_remittance(self.user)
        self.assertIsNone(result)

    def test_returns_remittance_when_draft_exists(self):
        """Returns the Remittance when a draft exists."""
        rem = Remittance.objects.create(
            date=timezone.localdate(),
            created_by=self.user,
            status=Remittance.StatusChoices.DRAFT,
        )
        result = selectors.get_today_remittance(self.user)
        self.assertEqual(result.pk, rem.pk)

    def test_returns_remittance_when_finalized_exists(self):
        """Returns the Remittance when finalized."""
        rem = Remittance.objects.create(
            date=timezone.localdate(),
            created_by=self.user,
            status=Remittance.StatusChoices.FINALIZED,
        )
        result = selectors.get_today_remittance(self.user)
        self.assertEqual(result.pk, rem.pk)


class RecentRemittancesSelectorTests(TestCase):
    """Tests for get_recent_remittances (returns raw values dicts)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="recent_user", password="securepassword123"
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_returns_empty_list_when_no_remittances(self):
        """Returns empty list when no remittances exist."""
        result = selectors.get_recent_remittances(self.user)
        self.assertEqual(result, [])

    def test_returns_up_to_eight_remittances(self):
        """Returns at most 8 remittances ordered by date descending."""
        today = timezone.localdate()
        for i in range(10):
            Remittance.objects.create(
                date=today - timedelta(days=i),
                created_by=self.user,
                total_sales=Decimal(f"{100 * (10 - i)}.00"),
                net_profit=Decimal("50.00"),
                tithe_amount=Decimal("10.00"),
                tithes_paid=True,
                offering_paid=True,
            )
        result = selectors.get_recent_remittances(self.user)
        self.assertEqual(len(result), 8)
        # Most recent first — raw date value, not formatted
        self.assertEqual(result[0]["date"], today)

    def test_raw_values_contain_db_fields(self):
        """Raw dicts contain unformatted DB values."""
        Remittance.objects.create(
            date=timezone.localdate(),
            created_by=self.user,
            total_sales=Decimal("100.00"),
            tithes_paid=True,
            offering_paid=True,
        )
        result = selectors.get_recent_remittances(self.user)
        self.assertEqual(result[0]["total_sales"], Decimal("100.00"))
        self.assertTrue(result[0]["tithes_paid"])
        self.assertTrue(result[0]["offering_paid"])


class OutstandingDebtCreditsTests(TestCase):
    """Tests for get_outstanding_debt_credits (returns CreditLine list)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="debts_user", password="securepassword123"
        )
        self.product = Product.objects.create(
            name="Alkaline", variation="Round", price=Decimal("40.00")
        )
        self.customer = Customer.objects.create(name="Debt Customer")
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_returns_empty_list_when_no_credit_lines(self):
        """Returns empty list when no outstanding credit lines exist."""
        result = selectors.get_outstanding_debt_credits(self.user)
        self.assertEqual(result, [])

    def test_returns_credit_lines_with_qty_remaining(self):
        """Returns credit lines with qty_remaining > 0."""
        CreditLine.objects.create(
            customer=self.customer,
            product=self.product,
            qty_credited=5,
            qty_remaining=3,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("200.00"),
        )
        result = selectors.get_outstanding_debt_credits(self.user)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].customer.name, "Debt Customer")
        self.assertEqual(result[0].qty_remaining, 3)

    def test_excludes_paid_off_credit_lines(self):
        """Credit lines with qty_remaining=0 are excluded."""
        CreditLine.objects.create(
            customer=self.customer,
            product=self.product,
            qty_credited=5,
            qty_remaining=0,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("200.00"),
        )
        result = selectors.get_outstanding_debt_credits(self.user)
        self.assertEqual(result, [])
