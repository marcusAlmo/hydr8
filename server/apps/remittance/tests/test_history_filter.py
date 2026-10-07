"""Tests for remittance history selectors and date filtering logic."""
from datetime import date, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import Product
from apps.customers.models import Customer
from apps.remittance.models import (
    Remittance,
    RemittanceRider,
    RemittanceRiderProductLine,
)
from apps.remittance.selectors import (
    get_recent_remittances,
    get_remittance_history_context,
)
from apps.settings.models import Company
from apps.users.models import Role, User


def _make_user(username: str, role_name: str, company: Company) -> User:
    role, _ = Role.objects.get_or_create(name=role_name, company=None)
    user = User.objects.create_user(
        username=username,
        password="securepassword123",
        first_name="Test",
        last_name=username.capitalize(),
    )
    user.role = role
    user.company = company
    user.save()
    return user


class RemittanceHistoryDateFilterTests(TestCase):
    """Tests for get_remittance_history_context and get_recent_remittances date filtering."""

    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="History Filter Station")
        self.admin = _make_user("admin_hist_filt", "Admin", self.company)
        self.driver = _make_user("driver_hist_filt", "Driver", self.company)

        self.product = Product.objects.create(
            name="Mineral Water 5G",
            category="water",
            price=Decimal("35.00"),
            company=self.company,
        )

        # Create sample remittances as DRAFT first (due to Postgres trigger immutability),
        # then finalize them after child records are attached.
        self.rem1 = Remittance.objects.create(
            company=self.company,
            created_by=self.admin,
            date=date(2026, 8, 15),
            status=Remittance.StatusChoices.DRAFT,
            total_sales=Decimal("5000.00"),
            total_commission=Decimal("500.00"),
            total_repayments_received=Decimal("200.00"),
            total_expenses=Decimal("300.00"),
            net_profit=Decimal("4400.00"),
            tithe_amount=Decimal("440.00"),
            offering_amount=Decimal("50.00"),
        )
        rr1 = RemittanceRider.objects.create(
            remittance=self.rem1,
            rider=self.driver,
            company=self.company,
        )
        RemittanceRiderProductLine.objects.create(
            remittance_rider=rr1,
            product=self.product,
            qty_sold=100,
            unit_price_snapshot=Decimal("35.00"),
            commission_rate_snapshot=Decimal("5.00"),
            subtotal_payable=Decimal("3500.00"),
            subtotal_credit=Decimal("0.00"),
            subtotal_commission=Decimal("500.00"),
            company=self.company,
        )
        self.rem1.status = Remittance.StatusChoices.FINALIZED
        self.rem1.save(update_fields=["status"])

        self.rem2 = Remittance.objects.create(
            company=self.company,
            created_by=self.admin,
            date=date(2026, 8, 20),
            status=Remittance.StatusChoices.DRAFT,
            total_sales=Decimal("7000.00"),
            total_commission=Decimal("700.00"),
            total_repayments_received=Decimal("300.00"),
            total_expenses=Decimal("400.00"),
            net_profit=Decimal("6200.00"),
            tithe_amount=Decimal("620.00"),
            offering_amount=Decimal("80.00"),
        )
        rr2 = RemittanceRider.objects.create(
            remittance=self.rem2,
            rider=self.driver,
            company=self.company,
        )
        RemittanceRiderProductLine.objects.create(
            remittance_rider=rr2,
            product=self.product,
            qty_sold=150,
            unit_price_snapshot=Decimal("35.00"),
            commission_rate_snapshot=Decimal("5.00"),
            subtotal_payable=Decimal("5250.00"),
            subtotal_credit=Decimal("0.00"),
            subtotal_commission=Decimal("750.00"),
            company=self.company,
        )
        self.rem2.status = Remittance.StatusChoices.FINALIZED
        self.rem2.save(update_fields=["status"])

    def tearDown(self):
        cache.clear()

    def test_explicit_narrow_date_range_within_90_days(self):
        """Specifying start_date and end_date within 90 days returns daily series."""
        ctx = get_remittance_history_context(
            self.admin,
            start_date=date(2026, 8, 14),
            end_date=date(2026, 8, 21),
        )
        trends = ctx["trends"]
        # Span from Aug 14 to Aug 21 inclusive is 8 days
        self.assertEqual(len(trends["labels"]), 8)
        self.assertEqual(len(trends["total_sales"]), 8)

        # Sum of sales in range should equal rem1 (5000) + rem2 (7000) = 12000
        self.assertEqual(sum(trends["total_sales"]), 12000.0)
        self.assertEqual(sum(trends["commissions_paid"]), 1200.0)
        self.assertEqual(sum(trends["total_repayments"]), 500.0)
        self.assertEqual(sum(trends["total_expenses"]), 700.0)
        self.assertEqual(sum(trends["net_profit"]), 10600.0)
        self.assertEqual(sum(trends["tithes"]), 1060.0)
        self.assertEqual(sum(trends["offerings"]), 130.0)

        # Per-rider units sold
        driver_entry = next(r for r in trends["riders"] if r["name"] == self.driver.full_name)
        self.assertEqual(sum(driver_entry["units_sold"]), 250)

    def test_wide_date_range_greater_than_90_days(self):
        """Specifying a wide range (e.g. 2001 to 2027) collapses to active remittance dates."""
        ctx = get_remittance_history_context(
            self.admin,
            start_date=date(2001, 1, 1),
            end_date=date(2027, 12, 31),
        )
        trends = ctx["trends"]
        # Instead of 9000+ daily points, collapses to the 2 active dates (Aug 15, Aug 20)
        self.assertEqual(len(trends["labels"]), 2)
        self.assertEqual(sum(trends["total_sales"]), 12000.0)

        # Rider totals match
        driver_entry = next(r for r in trends["riders"] if r["name"] == self.driver.full_name)
        self.assertEqual(sum(driver_entry["units_sold"]), 250)

    def test_inverted_date_range_swaps_automatically(self):
        """If start_date > end_date, dates are swapped transparently."""
        ctx = get_remittance_history_context(
            self.admin,
            start_date=date(2026, 8, 25),
            end_date=date(2026, 8, 10),
        )
        trends = ctx["trends"]
        self.assertEqual(sum(trends["total_sales"]), 12000.0)

    def test_recent_remittances_filters_by_date_range(self):
        """get_recent_remittances filters the table records by start_date and end_date."""
        # Range covering only rem1
        res = get_recent_remittances(
            self.admin,
            start_date=date(2026, 8, 14),
            end_date=date(2026, 8, 16),
        )
        self.assertEqual(res["total"], 1)
        self.assertEqual(res["remittances"][0]["id"], self.rem1.id)

        # Range covering both
        res_both = get_recent_remittances(
            self.admin,
            start_date=date(2026, 8, 14),
            end_date=date(2026, 8, 21),
        )
        self.assertEqual(res_both["total"], 2)

        # Range covering none
        res_none = get_recent_remittances(
            self.admin,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
        self.assertEqual(res_none["total"], 0)
