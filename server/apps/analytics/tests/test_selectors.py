"""Tests for the analytics dashboard selectors.

Covers all public and key private selector functions that build the
dashboard context from live operational data.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Product
from apps.customers.models import CreditLine, Customer
from apps.customers.services import record_customer_borrowed, record_customer_debt
from apps.remittance.models import Remittance
from apps.users.models import User

from apps.analytics.selectors import (
    _fmt_peso,
    _outstanding_debt,
    _outstanding_debts,
    _recent_remittances,
    _sales_for_date,
    _sales_trend,
    _unreturned_containers,
    _warning_banner,
    get_dashboard_context,
)


class FmtPesoTests(TestCase):
    """Tests for the _fmt_peso helper."""

    def test_formats_thousands(self):
        self.assertEqual(_fmt_peso(Decimal("1000.00")), "₱1,000.00")

    def test_formats_zero(self):
        self.assertEqual(_fmt_peso(Decimal("0.00")), "₱0.00")

    def test_formats_large_number(self):
        self.assertEqual(_fmt_peso(Decimal("1234567.89")), "₱1,234,567.89")

    def test_formats_small_decimal(self):
        self.assertEqual(_fmt_peso(Decimal("0.50")), "₱0.50")


class SalesForDateTests(TestCase):
    """Tests for _sales_for_date."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="sales_user", password="securepassword123"
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_returns_sales_when_remittance_exists(self):
        """Returns total_sales when a remittance exists for the target date."""
        today = timezone.localdate()
        Remittance.objects.create(
            date=today,
            created_by=self.user,
            total_sales=Decimal("500.00"),
        )
        result = _sales_for_date(self.user, today)
        self.assertEqual(result, Decimal("500.00"))

    def test_returns_zero_when_no_remittance(self):
        """Returns Decimal('0.00') when no remittance exists for the date."""
        result = _sales_for_date(self.user, timezone.localdate())
        self.assertEqual(result, Decimal("0.00"))


class SalesTrendTests(TestCase):
    """Tests for _sales_trend."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="trend_user", password="securepassword123"
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _create_remittance(self, date, sales):
        Remittance.objects.create(
            date=date,
            created_by=self.user,
            total_sales=Decimal(str(sales)),
        )

    def test_trend_up_when_sales_increased(self):
        """Trend is 'up' when today's sales > yesterday's."""
        today = timezone.localdate()
        self._create_remittance(today, 1000)
        self._create_remittance(today - timedelta(days=1), 500)
        _, _, direction = _sales_trend(self.user)
        self.assertEqual(direction, "up")

    def test_trend_down_when_sales_decreased(self):
        """Trend is 'down' when today's sales < yesterday's."""
        today = timezone.localdate()
        self._create_remittance(today, 500)
        self._create_remittance(today - timedelta(days=1), 1000)
        _, _, direction = _sales_trend(self.user)
        self.assertEqual(direction, "down")

    def test_trend_flat_when_no_yesterday_sales(self):
        """Trend is 'flat' when yesterday had no sales."""
        today = timezone.localdate()
        self._create_remittance(today, 1000)
        _, trend, direction = _sales_trend(self.user)
        self.assertEqual(direction, "flat")
        self.assertIn("No sales recorded yesterday", trend)

    def test_trend_flat_when_no_change(self):
        """Trend is 'flat' when sales are identical."""
        today = timezone.localdate()
        self._create_remittance(today, 1000)
        self._create_remittance(today - timedelta(days=1), 1000)
        _, _, direction = _sales_trend(self.user)
        self.assertEqual(direction, "flat")


class OutstandingDebtTests(TestCase):
    """Tests for _outstanding_debt."""

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
        c1 = Customer.objects.create(name="C1", debt_balance=Decimal("100.00"))
        c2 = Customer.objects.create(name="C2", debt_balance=Decimal("200.00"))
        result = _outstanding_debt(self.user)
        self.assertEqual(result, Decimal("300.00"))

    def test_returns_zero_when_no_customers(self):
        """Returns Decimal('0.00') when no customers exist."""
        result = _outstanding_debt(self.user)
        self.assertEqual(result, Decimal("0.00"))

    def test_excludes_deleted_customers(self):
        """Deleted customers are excluded from the sum."""
        from django.utils import timezone
        Customer.objects.create(
            name="Deleted",
            debt_balance=Decimal("500.00"),
            deleted_at=timezone.now(),
        )
        result = _outstanding_debt(self.user)
        self.assertEqual(result, Decimal("0.00"))


class UnreturnedContainersTests(TestCase):
    """Tests for _unreturned_containers."""

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
        result = _unreturned_containers(self.user)
        self.assertEqual(result["total"], 6)
        labels = [b["label"] for b in result["breakdown"]]
        self.assertIn("Round 8gal", labels)
        self.assertIn("Slim 8gal", labels)
        self.assertIn("Other", labels)

    def test_returns_zero_when_no_customers(self):
        """Returns total=0 when no customers exist."""
        result = _unreturned_containers(self.user)
        self.assertEqual(result["total"], 0)


class WarningBannerTests(TestCase):
    """Tests for _warning_banner."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="banner_user", password="securepassword123"
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_shows_banner_when_no_remittance_today(self):
        """Banner shows when no remittance exists for today."""
        banner = _warning_banner(self.user)
        self.assertTrue(banner["show"])
        self.assertIn("No remittance", banner["title"])

    def test_hides_banner_when_remittance_exists(self):
        """Banner is hidden when a remittance exists for today."""
        Remittance.objects.create(
            date=timezone.localdate(),
            created_by=self.user,
        )
        banner = _warning_banner(self.user)
        self.assertFalse(banner["show"])


class RecentRemittancesTests(TestCase):
    """Tests for _recent_remittances."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="recent_user", password="securepassword123"
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_returns_empty_list_when_no_remittances(self):
        """Returns empty list when no remittances exist."""
        result = _recent_remittances(self.user)
        self.assertEqual(result, [])

    def test_returns_up_to_five_remittances(self):
        """Returns at most 5 remittances ordered by date descending."""
        today = timezone.localdate()
        for i in range(7):
            Remittance.objects.create(
                date=today - timedelta(days=i),
                created_by=self.user,
                total_sales=Decimal(f"{100 * (7 - i)}.00"),
                net_profit=Decimal("50.00"),
                tithe_amount=Decimal("10.00"),
                tithes_paid=True,
                offering_paid=True,
            )
        result = _recent_remittances(self.user)
        self.assertEqual(len(result), 5)
        # Most recent first
        self.assertEqual(result[0]["date"], today.strftime("%b %d, %Y"))

    def test_tithes_status_paid_when_both_paid(self):
        """tithes_status is 'paid' when both tithes and offering are paid."""
        Remittance.objects.create(
            date=timezone.localdate(),
            created_by=self.user,
            tithes_paid=True,
            offering_paid=True,
        )
        result = _recent_remittances(self.user)
        self.assertEqual(result[0]["tithes_status"], "paid")
        self.assertFalse(result[0]["has_warning"])

    def test_tithes_status_unpaid_when_tithes_unpaid(self):
        """tithes_status is 'unpaid' when tithes are not paid."""
        Remittance.objects.create(
            date=timezone.localdate(),
            created_by=self.user,
            tithes_paid=False,
            offering_paid=True,
        )
        result = _recent_remittances(self.user)
        self.assertEqual(result[0]["tithes_status"], "unpaid")
        self.assertTrue(result[0]["has_warning"])


class OutstandingDebtsTests(TestCase):
    """Tests for _outstanding_debts."""

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
        result = _outstanding_debts(self.user)
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
        result = _outstanding_debts(self.user)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["customer"], "Debt Customer")
        self.assertEqual(result[0]["qty_remaining"], 3)
        self.assertEqual(result[0]["amount"], "₱120.00")
        self.assertIn("HY-", result[0]["customer_id"])

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
        result = _outstanding_debts(self.user)
        self.assertEqual(result, [])

    def test_severity_normal_for_recent_debt(self):
        """Severity is 'normal' for debt younger than 30 days."""
        CreditLine.objects.create(
            customer=self.customer,
            product=self.product,
            qty_credited=5,
            qty_remaining=3,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("200.00"),
        )
        result = _outstanding_debts(self.user)
        self.assertEqual(result[0]["severity"], "normal")

    def test_severity_critical_for_old_debt(self):
        """Severity is 'critical' for debt older than 45 days."""
        line = CreditLine.objects.create(
            customer=self.customer,
            product=self.product,
            qty_credited=5,
            qty_remaining=3,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("200.00"),
        )
        # Manually backdate the created_at
        from django.utils import timezone
        CreditLine.objects.filter(pk=line.pk).update(
            created_at=timezone.now() - timedelta(days=50)
        )
        result = _outstanding_debts(self.user)
        self.assertEqual(result[0]["severity"], "critical")


class GetDashboardContextTests(TestCase):
    """Tests for the public get_dashboard_context entry point."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="context_user", password="securepassword123"
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_returns_all_required_keys(self):
        """The context dict contains all required keys."""
        ctx = get_dashboard_context(self.user)
        expected_keys = {
            "today_date",
            "warning_banner",
            "stats",
            "recent_remittances",
            "outstanding_debts",
            "ai_insights",
        }
        self.assertEqual(set(ctx.keys()), expected_keys)

    def test_stats_has_three_cards(self):
        """The stats list contains exactly 3 stat cards."""
        ctx = get_dashboard_context(self.user)
        self.assertEqual(len(ctx["stats"]), 3)

    def test_ai_insights_is_empty_list(self):
        """ai_insights is an empty list (no AI insights configured)."""
        ctx = get_dashboard_context(self.user)
        self.assertEqual(ctx["ai_insights"], [])

    def test_today_date_is_formatted(self):
        """today_date is a formatted string."""
        ctx = get_dashboard_context(self.user)
        expected = timezone.localtime().strftime("%A, %b %d, %Y")
        self.assertEqual(ctx["today_date"], expected)
