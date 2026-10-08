"""Tests for sidebar navigation, HTMX boosting, and shell integration."""
from django.test import TestCase
from django.urls import reverse

from apps.settings.models import Company
from apps.users.models import Role, User


class SidebarNavigationTests(TestCase):
    """Verifies that all sidebar navigation routes respond properly to standard
    and boosted HTMX requests, and that base shell configurations are intact."""

    def setUp(self):
        self.company = Company.objects.create(name="Hydr8 Station Test")
        self.admin_role, _ = Role.objects.get_or_create(name="Admin", company=None)
        self.staff_role, _ = Role.objects.get_or_create(name="Staff", company=None)

        self.admin = User.objects.create_user(
            username="admin_nav",
            password="securepassword123",
            role=self.admin_role,
            company=self.company,
        )
        self.staff = User.objects.create_user(
            username="staff_nav",
            password="securepassword123",
            role=self.staff_role,
            company=self.company,
        )

    def test_sidebar_template_contains_hx_boost_and_exempts_logout(self):
        """The sidebar template must enable hx-boost and exempt the logout form."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        self.assertIn('hx-boost="true"', html)
        self.assertIn('hx-boost="false"', html)
        self.assertIn('hx-ext="head-support"', html)
        self.assertIn("head-support.js", html)

    def test_all_sidebar_links_respond_to_boosted_htmx_requests(self):
        """Every primary sidebar link returns HTTP 200 for boosted requests."""
        self.client.force_login(self.admin)

        routes = [
            ("analytics:dashboard", {}),
            ("remittance:history", {}),
            ("customers:list", {}),
            ("products:list", {}),
            ("employees:list", {}),
            ("settings:list", {}),
            ("audit:list", {}),
        ]

        for route_name, kwargs in routes:
            url = reverse(route_name, kwargs=kwargs)
            # Boosted navigation request sent by HTMX
            response = self.client.get(
                url,
                HTTP_HX_REQUEST="true",
                HTTP_HX_BOOSTED="true",
            )
            self.assertEqual(
                response.status_code,
                200,
                f"Boosted HTMX request to {route_name} failed with status {response.status_code}",
            )
            self.assertIn("hx-boost=\"true\"", response.content.decode())

    def test_staff_sidebar_navigation_boosted(self):
        """Staff navigation items respond properly to boosted requests."""
        self.client.force_login(self.staff)

        # Staff can access Add Remittance, Customers, and Settings Profile
        routes = [
            reverse("remittance:add"),
            reverse("customers:list"),
            reverse("settings:list") + "?tab=profile",
        ]

        for url in routes:
            response = self.client.get(
                url,
                HTTP_HX_REQUEST="true",
                HTTP_HX_BOOSTED="true",
            )
            self.assertEqual(
                response.status_code,
                200,
                f"Staff boosted request to {url} failed with status {response.status_code}",
            )
