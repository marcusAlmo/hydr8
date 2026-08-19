"""Tests for the Staff limited-access view.

Staff users get a focused view of the system:
  - Login redirects to the Add Remittance page (not the dashboard)
  - Dashboard, Remittance History, Products, Employees, Audit Log are blocked
  - Customers page is fully accessible
  - Settings page shows only the My Profile tab

Admin users and platform superusers retain full access to everything.
"""
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.users.models import Role, User


class StaffLimitedAccessTestCase(TestCase):
    """Shared setUp — creates Admin and Staff users with roles + PINs."""

    @classmethod
    def setUpTestData(cls):
        cls.admin_role, _ = Role.objects.get_or_create(name="Admin")
        cls.staff_role, _ = Role.objects.get_or_create(name="Staff")

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            username="admin_user",
            password="securepassword123",
            first_name="Ada",
            last_name="Min",
        )
        self.admin.role = self.admin_role
        self.admin.set_pin("1234")
        self.admin.save()

        self.staff = User.objects.create_user(
            username="staff_user",
            password="securepassword123",
            first_name="Sta",
            last_name="FF",
        )
        self.staff.role = self.staff_role
        self.staff.set_pin("1234")
        self.staff.save()

    def tearDown(self):
        cache.clear()


# ---------------------------------------------------------------------------
# Login redirect
# ---------------------------------------------------------------------------

class StaffLoginRedirectTests(StaffLimitedAccessTestCase):
    """Staff users land on Add Remittance; Admin lands on the dashboard."""

    def test_staff_login_redirects_to_add_remittance(self):
        """HTMX login for a Staff user sets HX-Redirect to /remittance/add/."""
        response = self.client.post(
            "/login/",
            {"username": "staff_user", "password": "securepassword123"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Redirect", response.headers)
        self.assertEqual(response.headers["HX-Redirect"], "/remittance/add/")

    def test_admin_login_redirects_to_dashboard(self):
        """HTMX login for an Admin user sets HX-Redirect to /analytics/dashboard/."""
        response = self.client.post(
            "/login/",
            {"username": "admin_user", "password": "securepassword123"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Redirect", response.headers)
        self.assertEqual(response.headers["HX-Redirect"], "/analytics/dashboard/")


# ---------------------------------------------------------------------------
# View-level access control — Staff blocked from Admin-only pages
# ---------------------------------------------------------------------------

class StaffViewAccessTests(StaffLimitedAccessTestCase):
    """Staff users receive 403 on Admin-only views; Admin users get 200."""

    def _staff_get(self, url):
        self.client.force_login(self.staff)
        return self.client.get(url)

    def _admin_get(self, url):
        self.client.force_login(self.admin)
        return self.client.get(url)

    # --- Dashboard ---
    def test_staff_blocked_from_dashboard(self):
        resp = self._staff_get(reverse("analytics:dashboard"))
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_access_dashboard(self):
        resp = self._admin_get(reverse("analytics:dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_staff_blocked_from_dashboard_stats_partial(self):
        resp = self._staff_get(reverse("analytics:dashboard_stats"))
        self.assertEqual(resp.status_code, 403)

    def test_staff_blocked_from_dashboard_recent_remittances_partial(self):
        resp = self._staff_get(reverse("analytics:dashboard_recent_remittances"))
        self.assertEqual(resp.status_code, 403)

    def test_staff_blocked_from_dashboard_outstanding_debts_partial(self):
        resp = self._staff_get(reverse("analytics:dashboard_outstanding_debts"))
        self.assertEqual(resp.status_code, 403)

    # --- Remittance History ---
    def test_staff_blocked_from_remittance_history(self):
        resp = self._staff_get(reverse("remittance:history"))
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_access_remittance_history(self):
        resp = self._admin_get(reverse("remittance:history"))
        self.assertEqual(resp.status_code, 200)

    # --- Remittance Add (Staff CAN access) ---
    def test_staff_can_access_add_remittance(self):
        resp = self._staff_get(reverse("remittance:add"))
        self.assertEqual(resp.status_code, 200)

    def test_admin_can_access_add_remittance(self):
        resp = self._admin_get(reverse("remittance:add"))
        self.assertEqual(resp.status_code, 200)

    # --- Products ---
    def test_staff_blocked_from_products(self):
        resp = self._staff_get(reverse("products:list"))
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_access_products(self):
        resp = self._admin_get(reverse("products:list"))
        self.assertEqual(resp.status_code, 200)

    # --- Employees ---
    def test_staff_blocked_from_employees_directory(self):
        resp = self._staff_get(reverse("employees:list"))
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_access_employees_directory(self):
        resp = self._admin_get(reverse("employees:list"))
        self.assertEqual(resp.status_code, 200)

    # --- Audit Log ---
    def test_staff_blocked_from_audit_log(self):
        resp = self._staff_get(reverse("audit:list"))
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_access_audit_log(self):
        resp = self._admin_get(reverse("audit:list"))
        self.assertEqual(resp.status_code, 200)

    # --- Customers (Staff CAN access) ---
    def test_staff_can_access_customers(self):
        resp = self._staff_get(reverse("customers:list"))
        self.assertEqual(resp.status_code, 200)

    def test_admin_can_access_customers(self):
        resp = self._admin_get(reverse("customers:list"))
        self.assertEqual(resp.status_code, 200)

    # --- Settings (both can access, but Staff sees only profile) ---
    def test_staff_can_access_settings(self):
        resp = self._staff_get(reverse("settings:list"))
        self.assertEqual(resp.status_code, 200)

    def test_admin_can_access_settings(self):
        resp = self._admin_get(reverse("settings:list"))
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Settings tab filtering
# ---------------------------------------------------------------------------

class StaffSettingsTabTests(StaffLimitedAccessTestCase):
    """Staff users see only the My Profile tab in Settings."""

    def test_staff_sees_only_profile_tab(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("settings:list"))
        self.assertEqual(resp.status_code, 200)
        # Profile tab is present
        self.assertContains(resp, "My Profile")
        # System Config and Company tabs are NOT rendered
        self.assertNotContains(resp, "System Config")
        self.assertNotContains(resp, ">Company<")

    def test_staff_initial_tab_is_profile(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("settings:list"))
        self.assertContains(resp, "activeTab: 'profile'")

    def test_staff_initial_tab_ignores_tab_param(self):
        """Staff can't force ?tab=system-config — it always falls back to profile."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("settings:list") + "?tab=system-config")
        self.assertContains(resp, "activeTab: 'profile'")

    def test_staff_settings_does_not_render_system_config_section(self):
        """The system-config HTML section is not in the DOM for Staff."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("settings:list"))
        self.assertNotContains(resp, "activeTab === 'system-config'")

    def test_admin_sees_all_tabs(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("settings:list"))
        self.assertContains(resp, "System Config")
        self.assertContains(resp, "My Profile")
        # The Company tab label appears in the tab nav
        self.assertContains(resp, "Company")

    def test_admin_initial_tab_defaults_to_system_config(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("settings:list"))
        self.assertContains(resp, "activeTab: 'system-config'")


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

class StaffSidebarTests(StaffLimitedAccessTestCase):
    """The sidebar shows only Remittance, Customers, and Settings for Staff."""

    def test_staff_sidebar_omits_dashboard_link(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("customers:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "/analytics/dashboard/")

    def test_staff_sidebar_omits_products_link(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("customers:list"))
        self.assertNotContains(resp, "/products/")

    def test_staff_sidebar_omits_employees_link(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("customers:list"))
        self.assertNotContains(resp, "/employees/")

    def test_staff_sidebar_omits_audit_link(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("customers:list"))
        self.assertNotContains(resp, "/audit/")

    def test_staff_sidebar_remittance_links_to_add(self):
        """Staff sidebar Remittance link points to /remittance/add/ (not history)."""
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("customers:list"))
        self.assertContains(resp, "/remittance/add/")

    def test_staff_sidebar_does_not_link_to_remittance_history(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("customers:list"))
        self.assertNotContains(resp, "/remittance/history/")

    def test_staff_sidebar_shows_customers_link(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("customers:list"))
        self.assertContains(resp, "/customers/")

    def test_staff_sidebar_shows_settings_link(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("customers:list"))
        self.assertContains(resp, "/settings/?tab=profile")

    def test_admin_sidebar_shows_dashboard_link(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("customers:list"))
        self.assertContains(resp, "/analytics/dashboard/")

    def test_admin_sidebar_remittance_links_to_history(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("customers:list"))
        self.assertContains(resp, "/remittance/history/")


# ---------------------------------------------------------------------------
# Context processor
# ---------------------------------------------------------------------------

class StaffContextProcessorTests(StaffLimitedAccessTestCase):
    """The user_role_flags context processor exposes role flags to templates."""

    def test_staff_flags_exposed_for_staff_user(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("customers:list"))
        self.assertTrue(resp.context.get("is_staff_role_user"))
        self.assertFalse(resp.context.get("is_admin_user"))
        self.assertTrue(resp.context.get("is_back_office_user"))

    def test_staff_flags_exposed_for_admin_user(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("customers:list"))
        self.assertFalse(resp.context.get("is_staff_role_user"))
        self.assertTrue(resp.context.get("is_admin_user"))
        self.assertTrue(resp.context.get("is_back_office_user"))

    def test_flags_not_exposed_for_anonymous_user(self):
        resp = self.client.get(reverse("users:index"))
        self.assertFalse(resp.context.get("is_staff_role_user"))
        self.assertFalse(resp.context.get("is_admin_user"))
        self.assertFalse(resp.context.get("is_back_office_user"))


# ---------------------------------------------------------------------------
# Permissions helper
# ---------------------------------------------------------------------------

class IsStaffRoleHelperTests(StaffLimitedAccessTestCase):
    """Unit tests for the is_staff_role permission helper."""

    def test_staff_role_returns_true(self):
        from apps.users.permissions import is_staff_role
        self.assertTrue(is_staff_role(self.staff))

    def test_admin_role_returns_false(self):
        from apps.users.permissions import is_staff_role
        self.assertFalse(is_staff_role(self.admin))

    def test_superuser_returns_false(self):
        from apps.users.permissions import is_staff_role
        su = User.objects.create_user(
            username="super", password="pw", is_superuser=True
        )
        self.assertFalse(is_staff_role(su))

    def test_anonymous_returns_false(self):
        from django.contrib.auth.models import AnonymousUser

        from apps.users.permissions import is_staff_role
        self.assertFalse(is_staff_role(AnonymousUser()))

    def test_user_without_role_returns_false(self):
        from apps.users.permissions import is_staff_role
        plain = User.objects.create_user(username="plain", password="pw")
        self.assertFalse(is_staff_role(plain))
