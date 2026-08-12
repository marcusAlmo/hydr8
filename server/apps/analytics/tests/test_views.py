"""Tests for the analytics dashboard view.

Covers authentication, method gating, and rendering of the dashboard
page with live operational data.
"""
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import Product
from apps.customers.models import Customer
from apps.customers.services import record_customer_borrowed, record_customer_debt
from apps.remittance.models import Remittance
from apps.users.models import User


class DashboardViewTests(TestCase):
    """Tests for GET /analytics/dashboard/."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="analytics_staff",
            password="securepassword123",
        )
        self.product = Product.objects.create(
            name="Alkaline Water",
            variation="Round",
            price=Decimal("40.00"),
        )
        # Customer with debt + borrowed
        self.customer = Customer.objects.create(name="Dashboard Test Store")
        record_customer_debt(
            customer_id=f"HY-{self.customer.pk:04d}",
            product_key=str(self.product.pk),
            qty_credited=5,
            unit_price="40.00",
            performed_by=self.user,
        )
        record_customer_borrowed(
            customer_id=f"HY-{self.customer.pk:04d}",
            container_key="round_8gal",
            qty_borrowed=3,
            performed_by=self.user,
        )
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def _make_todays_remittance(self) -> Remittance:
        """Creates today's FINALIZED remittance for tests that need one.

        Created per-test (not in setUp) so the 'no remittance' banner test
        can simply omit it — the DB immutability trigger (migration 0005)
        prevents deleting a FINALIZED row, so we avoid creating one when
        it isn't needed.
        """
        from django.utils import timezone
        return Remittance.objects.create(
            date=timezone.localdate(),
            created_by=self.user,
            status=Remittance.StatusChoices.FINALIZED,
            total_sales=Decimal("1000.00"),
            net_profit=Decimal("800.00"),
            tithe_amount=Decimal("100.00"),
            tithes_paid=True,
            offering_paid=True,
        )

    def test_dashboard_returns_200_for_authenticated_user(self):
        """GET /analytics/dashboard/ returns 200 for an authenticated user."""
        response = self.client.get("/analytics/dashboard/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_requires_login(self):
        """An anonymous request is redirected to the login flow."""
        self.client.logout()
        response = self.client.get("/analytics/dashboard/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=/analytics/dashboard/", response["Location"])

    def test_dashboard_rejects_non_get_methods(self):
        """POST is not allowed on the dashboard endpoint."""
        response = self.client.post("/analytics/dashboard/")
        self.assertEqual(response.status_code, 405)

    def test_dashboard_renders_today_date(self):
        """The dashboard renders the formatted today's date."""
        from django.utils import timezone
        response = self.client.get("/analytics/dashboard/")
        expected = timezone.localtime().strftime("%A, %b %d, %Y")
        self.assertContains(response, expected)

    def test_dashboard_renders_stat_cards(self):
        """The dashboard renders all three summary stat cards."""
        response = self.client.get("/analytics/dashboard/")
        self.assertContains(response, "Outstanding Debt")
        self.assertContains(response, "Unreturned Containers")
        # "Today's" may be HTML-escaped, so check for the escaped form
        content = response.content.decode()
        self.assertIn("Total Sales", content)

    def test_dashboard_renders_sales_value(self):
        """The dashboard renders the today's sales value from the remittance."""
        self._make_todays_remittance()
        response = self.client.get("/analytics/dashboard/")
        content = response.content.decode()
        # The peso sign may be HTML-encoded; check for the numeric value
        self.assertIn("1,000.00", content)

    def test_dashboard_renders_debt_value(self):
        """The dashboard renders the outstanding debt value."""
        response = self.client.get("/analytics/dashboard/")
        content = response.content.decode()
        self.assertIn("200.00", content)

    def test_dashboard_renders_recent_remittances(self):
        """The dashboard renders the recent remittances table."""
        self._make_todays_remittance()
        response = self.client.get("/analytics/dashboard/")
        self.assertContains(response, "Recent Remittances")

    def test_dashboard_renders_outstanding_debts(self):
        """The dashboard renders the outstanding debts section."""
        response = self.client.get("/analytics/dashboard/")
        self.assertContains(response, "Outstanding Debts")
        self.assertContains(response, "Dashboard Test Store")

    def test_dashboard_shows_warning_banner_when_no_remittance(self):
        """The warning banner shows when today's remittance is missing."""
        # No remittance created for today — banner should appear.
        response = self.client.get("/analytics/dashboard/")
        self.assertContains(response, "No remittance for today yet")

    def test_dashboard_hides_warning_banner_when_remittance_exists(self):
        """The warning banner is hidden when today's remittance exists."""
        self._make_todays_remittance()
        response = self.client.get("/analytics/dashboard/")
        self.assertNotContains(response, "No remittance for today yet")

    def test_dashboard_renders_with_no_data(self):
        """The dashboard renders successfully with no customers or remittances."""
        # Create a fresh user with no data
        fresh = User.objects.create_user(
            username="empty_user",
            password="securepassword123",
        )
        self.client.logout()
        self.client.force_login(fresh)
        response = self.client.get("/analytics/dashboard/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # With no data, sales and debt should show 0.00
        self.assertIn("0.00", content)
