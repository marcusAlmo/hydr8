"""Tests for the analytics dashboard presentation layer.

Presentation functions take raw data (Decimals, model instances, raw
dicts) and shape them into template-ready dicts with formatted strings,
CSS classes, and card structures.
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

from apps.analytics.presentation import (
    apply_accent_classes,
    build_container_breakdown,
    build_outstanding_debt_row,
    build_recent_remittance_row,
    build_stats_cards,
    build_today_remittance_status,
    fmt_peso,
    format_sales_trend,
)


class FmtPesoTests(TestCase):
    """Tests for fmt_peso."""

    def test_formats_thousands(self):
        self.assertEqual(fmt_peso(Decimal("1000.00")), "₱1,000.00")

    def test_formats_zero(self):
        self.assertEqual(fmt_peso(Decimal("0.00")), "₱0.00")

    def test_formats_large_number(self):
        self.assertEqual(fmt_peso(Decimal("1234567.89")), "₱1,234,567.89")

    def test_formats_small_decimal(self):
        self.assertEqual(fmt_peso(Decimal("0.50")), "₱0.50")


class FormatSalesTrendTests(TestCase):
    """Tests for format_sales_trend."""

    def test_trend_up_when_sales_increased(self):
        _, direction = format_sales_trend(Decimal("1000"), Decimal("500"))
        self.assertEqual(direction, "up")

    def test_trend_down_when_sales_decreased(self):
        _, direction = format_sales_trend(Decimal("500"), Decimal("1000"))
        self.assertEqual(direction, "down")

    def test_trend_flat_when_no_yesterday_sales(self):
        trend, direction = format_sales_trend(Decimal("1000"), Decimal("0"))
        self.assertEqual(direction, "flat")
        self.assertIn("No sales recorded yesterday", trend)

    def test_trend_flat_when_no_change(self):
        _, direction = format_sales_trend(Decimal("1000"), Decimal("1000"))
        self.assertEqual(direction, "flat")


class BuildContainerBreakdownTests(TestCase):
    """Tests for build_container_breakdown."""

    def test_sums_counts(self):
        result = build_container_breakdown(3, 2, 1)
        self.assertEqual(result["total"], 6)
        labels = [b["label"] for b in result["breakdown"]]
        self.assertIn("Round 8gal", labels)
        self.assertIn("Slim 8gal", labels)
        self.assertIn("Other", labels)

    def test_zero_counts(self):
        result = build_container_breakdown(0, 0, 0)
        self.assertEqual(result["total"], 0)


class BuildStatsCardsTests(TestCase):
    """Tests for build_stats_cards."""

    def test_returns_three_cards(self):
        containers = build_container_breakdown(3, 2, 1)
        cards = build_stats_cards(
            today_sales=Decimal("500.00"),
            sales_trend="+10.0% from yesterday",
            sales_direction="up",
            outstanding_debt=Decimal("200.00"),
            containers=containers,
        )
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[0]["key"], "today_sales")
        self.assertEqual(cards[0]["value"], "₱500.00")
        self.assertEqual(cards[1]["key"], "outstanding_debt")
        self.assertEqual(cards[1]["value"], "₱200.00")
        self.assertEqual(cards[2]["key"], "unreturned_containers")
        self.assertEqual(cards[2]["value"], "6")


class BuildTodayRemittanceStatusTests(TestCase):
    """Tests for build_today_remittance_status."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="status_user", password="securepassword123"
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_state_none_when_no_remittance(self):
        result = build_today_remittance_status(None)
        self.assertEqual(result["state"], "none")
        self.assertIn("No remittance", result["title"])
        self.assertEqual(result["cta_url"], "remittance:add")

    def test_state_draft_when_draft_exists(self):
        rem = Remittance.objects.create(
            date=timezone.localdate(),
            created_by=self.user,
            status=Remittance.StatusChoices.DRAFT,
        )
        result = build_today_remittance_status(rem)
        self.assertEqual(result["state"], "draft")
        self.assertEqual(result["cta_url"], "remittance:add")

    def test_state_finalized_when_finalized_exists(self):
        rem = Remittance.objects.create(
            date=timezone.localdate(),
            created_by=self.user,
            status=Remittance.StatusChoices.FINALIZED,
        )
        result = build_today_remittance_status(rem)
        self.assertEqual(result["state"], "finalized")
        self.assertEqual(result["cta_url"], "remittance:history")


class BuildRecentRemittanceRowTests(TestCase):
    """Tests for build_recent_remittance_row."""

    def test_formats_date_and_currency(self):
        today = timezone.localdate()
        raw = {
            "date": today,
            "total_sales": Decimal("100.00"),
            "net_profit": Decimal("50.00"),
            "tithe_amount": Decimal("10.00"),
            "tithes_paid": True,
            "offering_paid": True,
        }
        row = build_recent_remittance_row(raw)
        self.assertEqual(row["date"], today.strftime("%b %d, %Y"))
        self.assertEqual(row["total_sales"], "₱100.00")
        self.assertEqual(row["net_profit"], "₱50.00")
        self.assertEqual(row["tithes"], "₱10.00")
        self.assertEqual(row["tithes_status"], "paid")
        self.assertFalse(row["has_warning"])

    def test_tithes_status_unpaid_when_tithes_unpaid(self):
        raw = {
            "date": timezone.localdate(),
            "total_sales": Decimal("100.00"),
            "net_profit": Decimal("50.00"),
            "tithe_amount": Decimal("10.00"),
            "tithes_paid": False,
            "offering_paid": True,
        }
        row = build_recent_remittance_row(raw)
        self.assertEqual(row["tithes_status"], "unpaid")
        self.assertTrue(row["has_warning"])


class BuildOutstandingDebtRowTests(TestCase):
    """Tests for build_outstanding_debt_row."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="debt_row_user", password="securepassword123"
        )
        self.product = Product.objects.create(
            name="Alkaline", variation="Round", price=Decimal("40.00")
        )
        self.customer = Customer.objects.create(name="Debt Customer")
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_formats_row_with_customer_and_amount(self):
        credit = CreditLine.objects.create(
            customer=self.customer,
            product=self.product,
            qty_credited=5,
            qty_remaining=3,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("200.00"),
        )
        today = timezone.localdate()
        row = build_outstanding_debt_row(credit, today)
        self.assertEqual(row["customer"], "Debt Customer")
        self.assertEqual(row["qty_remaining"], 3)
        self.assertEqual(row["amount"], "₱120.00")
        self.assertIn("HY-", row["customer_id"])

    def test_severity_normal_for_recent_debt(self):
        credit = CreditLine.objects.create(
            customer=self.customer,
            product=self.product,
            qty_credited=5,
            qty_remaining=3,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("200.00"),
        )
        today = timezone.localdate()
        row = build_outstanding_debt_row(credit, today)
        self.assertEqual(row["severity"], "normal")

    def test_severity_critical_for_old_debt(self):
        credit = CreditLine.objects.create(
            customer=self.customer,
            product=self.product,
            qty_credited=5,
            qty_remaining=3,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("200.00"),
        )
        CreditLine.objects.filter(pk=credit.pk).update(
            created_at=timezone.now() - timedelta(days=50)
        )
        credit.refresh_from_db()
        today = timezone.localdate()
        row = build_outstanding_debt_row(credit, today)
        self.assertEqual(row["severity"], "critical")


class ApplyAccentClassesTests(TestCase):
    """Tests for apply_accent_classes."""

    def test_applies_primary_classes(self):
        stats = [{"accent": "primary"}]
        apply_accent_classes(stats)
        self.assertEqual(stats[0]["border_class"], "border-t-primary")
        self.assertEqual(stats[0]["icon_class"], "text-primary")

    def test_applies_error_classes(self):
        stats = [{"accent": "error"}]
        apply_accent_classes(stats)
        self.assertEqual(stats[0]["border_class"], "border-t-error")
        self.assertEqual(stats[0]["icon_class"], "text-error")

    def test_defaults_to_primary_for_unknown_accent(self):
        stats = [{"accent": "unknown"}]
        apply_accent_classes(stats)
        self.assertEqual(stats[0]["border_class"], "border-t-primary")
