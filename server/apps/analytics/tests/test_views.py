"""Tests for the analytics dashboard view and HTMX lazy-load partials.

The dashboard is now split into a lightweight shell (header + skeletons +
today-remittance panel) and three HTMX partial endpoints that fetch the
heavy data (stats, recent remittances, outstanding debts).  Tests cover
both the shell and each partial.
"""
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Product
from apps.customers.models import Customer
from apps.customers.services import record_customer_borrowed, record_customer_debt
from apps.remittance.models import Remittance
from apps.users.models import Role, User


def _make_admin_user(username: str, password: str = "securepassword123") -> User:
    """Creates a user with the Admin role (required for dashboard access)."""
    admin_role, _ = Role.objects.get_or_create(name="Admin")
    user = User.objects.create_user(username=username, password=password)
    user.role = admin_role
    user.save()
    return user


class DashboardShellTests(TestCase):
    """Tests for GET /analytics/dashboard/ (the shell with skeletons)."""

    def setUp(self):
        self.user = _make_admin_user("analytics_admin")
        self.product = Product.objects.create(
            name="Alkaline Water",
            variation="Round",
            price=Decimal("40.00"),
        )
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
        """Creates today's FINALIZED remittance for tests that need one."""
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

    # --- Shell: basic HTTP behaviour ---

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

    # --- Shell: lightweight content ---

    def test_dashboard_renders_today_date(self):
        """The dashboard shell renders the formatted today's date."""
        response = self.client.get("/analytics/dashboard/")
        expected = timezone.localtime().strftime("%A, %b %d, %Y")
        self.assertContains(response, expected)

    def test_dashboard_renders_skeletons(self):
        """The shell renders skeleton placeholders for lazy-loaded sections."""
        response = self.client.get("/analytics/dashboard/")
        self.assertContains(response, "hydr8-skeleton")
        self.assertContains(response, "hx-get")
        self.assertContains(response, "/analytics/dashboard/partials/stats/")
        self.assertContains(
            response, "/analytics/dashboard/partials/recent-remittances/"
        )
        self.assertContains(
            response, "/analytics/dashboard/partials/outstanding-debts/"
        )

    def test_dashboard_does_not_render_stat_values_in_shell(self):
        """The shell should NOT contain the actual stat values (those are
        in the HTMX partial now)."""
        response = self.client.get("/analytics/dashboard/")
        # The stat labels are in the partial, not the shell
        self.assertNotContains(response, "Outstanding Debt")
        self.assertNotContains(response, "Unreturned Containers")

    def test_dashboard_shows_create_cta_when_no_remittance(self):
        """The Today's Remittance panel shows the create CTA when today's
        remittance is missing."""
        response = self.client.get("/analytics/dashboard/")
        self.assertContains(response, "No remittance for today yet")
        self.assertContains(response, "Create a Remittance")

    def test_dashboard_shows_finalized_state_when_remittance_exists(self):
        """The Today's Remittance panel shows the finalized state when
        today's remittance exists."""
        self._make_todays_remittance()
        response = self.client.get("/analytics/dashboard/")
        self.assertNotContains(response, "No remittance for today yet")
        # Use html=True because Django autoescapes the apostrophe in "Today's"
        self.assertContains(
            response, "Today's remittance is finalized", html=True
        )

    def test_dashboard_renders_with_no_data(self):
        """The dashboard shell renders successfully with no data at all."""
        fresh = _make_admin_user("empty_admin")
        self.client.logout()
        self.client.force_login(fresh)
        response = self.client.get("/analytics/dashboard/")
        self.assertEqual(response.status_code, 200)


class DashboardStatsPartialTests(TestCase):
    """Tests for GET /analytics/dashboard/partials/stats/."""

    def setUp(self):
        self.user = _make_admin_user("stats_admin")
        self.product = Product.objects.create(
            name="Alkaline Water",
            variation="Round",
            price=Decimal("40.00"),
        )
        self.customer = Customer.objects.create(name="Stats Test Store")
        record_customer_debt(
            customer_id=f"HY-{self.customer.pk:04d}",
            product_key=str(self.product.pk),
            qty_credited=5,
            unit_price="40.00",
            performed_by=self.user,
        )
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_stats_partial_returns_200(self):
        response = self.client.get("/analytics/dashboard/partials/stats/")
        self.assertEqual(response.status_code, 200)

    def test_stats_partial_requires_login(self):
        self.client.logout()
        response = self.client.get("/analytics/dashboard/partials/stats/")
        self.assertEqual(response.status_code, 302)

    def test_stats_partial_renders_cards(self):
        """The stats partial renders all three summary stat cards."""
        response = self.client.get("/analytics/dashboard/partials/stats/")
        self.assertContains(response, "Outstanding Debt")
        self.assertContains(response, "Unreturned Containers")
        self.assertContains(response, "Total Sales")

    def test_stats_partial_renders_debt_value(self):
        """The stats partial renders the outstanding debt value."""
        response = self.client.get("/analytics/dashboard/partials/stats/")
        self.assertContains(response, "200.00")

    def test_stats_partial_has_countup_animation(self):
        """The stats partial includes the Alpine countUp component."""
        response = self.client.get("/analytics/dashboard/partials/stats/")
        self.assertContains(response, "countUp")
        self.assertContains(response, "target:")

    def test_stats_partial_has_reveal_animation(self):
        """The stats partial includes the reveal animation class."""
        response = self.client.get("/analytics/dashboard/partials/stats/")
        self.assertContains(response, "hydr8-reveal")

    def test_stats_partial_renders_sales_value(self):
        """The stats partial renders today's sales value from the remittance."""
        Remittance.objects.create(
            date=timezone.localdate(),
            created_by=self.user,
            status=Remittance.StatusChoices.FINALIZED,
            total_sales=Decimal("1000.00"),
            net_profit=Decimal("800.00"),
            tithe_amount=Decimal("100.00"),
            tithes_paid=True,
            offering_paid=True,
        )
        response = self.client.get("/analytics/dashboard/partials/stats/")
        self.assertContains(response, "1,000.00")


class DashboardRecentRemittancesPartialTests(TestCase):
    """Tests for GET /analytics/dashboard/partials/recent-remittances/."""

    def setUp(self):
        self.user = _make_admin_user("rem_admin")
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_recent_remittances_partial_returns_200(self):
        response = self.client.get(
            "/analytics/dashboard/partials/recent-remittances/"
        )
        self.assertEqual(response.status_code, 200)

    def test_recent_remittances_partial_requires_login(self):
        self.client.logout()
        response = self.client.get(
            "/analytics/dashboard/partials/recent-remittances/"
        )
        self.assertEqual(response.status_code, 302)

    def test_recent_remittances_partial_renders_table(self):
        """The partial renders the recent remittances table header."""
        response = self.client.get(
            "/analytics/dashboard/partials/recent-remittances/"
        )
        self.assertContains(response, "Recent Remittances")

    def test_recent_remittances_partial_has_reveal_animation(self):
        response = self.client.get(
            "/analytics/dashboard/partials/recent-remittances/"
        )
        self.assertContains(response, "hydr8-reveal")

    def test_recent_remittances_partial_shows_data(self):
        """The partial renders remittance row data."""
        Remittance.objects.create(
            date=timezone.localdate(),
            created_by=self.user,
            status=Remittance.StatusChoices.FINALIZED,
            total_sales=Decimal("1000.00"),
            net_profit=Decimal("800.00"),
            tithe_amount=Decimal("100.00"),
            tithes_paid=True,
            offering_paid=True,
        )
        response = self.client.get(
            "/analytics/dashboard/partials/recent-remittances/"
        )
        self.assertContains(response, "1,000.00")


class DashboardOutstandingDebtsPartialTests(TestCase):
    """Tests for GET /analytics/dashboard/partials/outstanding-debts/."""

    def setUp(self):
        self.user = _make_admin_user("debts_admin")
        self.product = Product.objects.create(
            name="Alkaline Water",
            variation="Round",
            price=Decimal("40.00"),
        )
        self.customer = Customer.objects.create(name="Debts Test Store")
        record_customer_debt(
            customer_id=f"HY-{self.customer.pk:04d}",
            product_key=str(self.product.pk),
            qty_credited=5,
            unit_price="40.00",
            performed_by=self.user,
        )
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_outstanding_debts_partial_returns_200(self):
        response = self.client.get(
            "/analytics/dashboard/partials/outstanding-debts/"
        )
        self.assertEqual(response.status_code, 200)

    def test_outstanding_debts_partial_requires_login(self):
        self.client.logout()
        response = self.client.get(
            "/analytics/dashboard/partials/outstanding-debts/"
        )
        self.assertEqual(response.status_code, 302)

    def test_outstanding_debts_partial_renders_section(self):
        """The partial renders the outstanding debts section."""
        response = self.client.get(
            "/analytics/dashboard/partials/outstanding-debts/"
        )
        self.assertContains(response, "Outstanding Debts")
        self.assertContains(response, "Debts Test Store")

    def test_outstanding_debts_partial_has_reveal_animation(self):
        response = self.client.get(
            "/analytics/dashboard/partials/outstanding-debts/"
        )
        self.assertContains(response, "hydr8-reveal")
