"""Tests for apps.users.views_employees — HTTP endpoints for the Employees & Users directory."""
from django.core.cache import cache
from django.test import TestCase

from apps.users.models import Role, User


class EmployeesDirectoryViewTests(TestCase):
    """Tests for the main page render — GET /employees/."""

    def setUp(self):
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.staff_role, _ = Role.objects.get_or_create(name="Staff")
        self.driver_role, _ = Role.objects.get_or_create(name="Driver")

        self.admin = User.objects.create_user(
            username="admin", password="pw1234567",
        )
        self.admin.role = self.admin_role
        self.admin.save()

        self.staff = User.objects.create_user(
            username="staff", password="pw1234567",
        )
        self.staff.role = self.staff_role
        self.staff.save()

        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_page_renders_200_for_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get("/employees/")
        self.assertEqual(response.status_code, 200)

    def test_requires_login(self):
        response = self.client.get("/employees/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("next", response.url)

    def test_staff_gets_403(self):
        """Staff role does not have access to the Employees directory."""
        self.client.force_login(self.staff)
        response = self.client.get("/employees/")
        self.assertEqual(response.status_code, 403)

    def test_rejects_non_get_methods(self):
        self.client.force_login(self.admin)
        response = self.client.post("/employees/")
        self.assertEqual(response.status_code, 405)

    def test_page_contains_directory_heading(self):
        self.client.force_login(self.admin)
        response = self.client.get("/employees/")
        self.assertContains(response, "Employees")

    def test_page_contains_roles_tab(self):
        self.client.force_login(self.admin)
        response = self.client.get("/employees/")
        self.assertContains(response, "Roles")


class EmployeesSearchViewTests(TestCase):
    """Tests for the HTMX search endpoint — GET /employees/search/."""

    def setUp(self):
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.admin = User.objects.create_user(
            username="admin", password="pw1234567",
            first_name="Alice", last_name="Admin",
        )
        self.admin.role = self.admin_role
        self.admin.save()

        self.driver = User.objects.create_user(
            username="driver1", password="pw1234567",
            first_name="Dave", last_name="Driver",
        )
        self.driver.role = Role.objects.get_or_create(name="Driver")[0]
        self.driver.save()

        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_search_returns_200_for_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get("/employees/search/", HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)

    def test_search_filters_by_name(self):
        self.client.force_login(self.admin)
        response = self.client.get("/employees/search/?q=Dave", HTTP_HX_REQUEST="true")
        self.assertContains(response, "Dave")
        self.assertNotContains(response, "Alice")

    def test_search_requires_login(self):
        response = self.client.get("/employees/search/")
        self.assertEqual(response.status_code, 302)


class UserDetailViewTests(TestCase):
    """Tests for the HTMX user detail endpoint — GET /employees/user/<id>/."""

    def setUp(self):
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.driver_role, _ = Role.objects.get_or_create(name="Driver")
        self.staff_role, _ = Role.objects.get_or_create(name="Staff")

        self.admin = User.objects.create_user(
            username="admin", password="pw1234567",
        )
        self.admin.role = self.admin_role
        self.admin.save()

        self.driver = User.objects.create_user(
            username="driver1", password="pw1234567",
        )
        self.driver.role = self.driver_role
        self.driver.save()

        self.staff_user = User.objects.create_user(
            username="staff1", password="pw1234567",
        )
        self.staff_user.role = self.staff_role
        self.staff_user.save()

        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_detail_returns_200_for_existing_user(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            f"/employees/user/{self.driver.id}/", HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)

    def test_detail_returns_404_for_missing_user(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            "/employees/user/00000000-0000-0000-0000-000000000000/",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 404)

    def test_detail_requires_login(self):
        response = self.client.get(f"/employees/user/{self.driver.id}/")
        self.assertEqual(response.status_code, 302)

    def test_detail_staff_gets_403(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(f"/employees/user/{self.driver.id}/")
        self.assertEqual(response.status_code, 403)

    def test_detail_driver_context_has_driver_stats(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            f"/employees/user/{self.driver.id}/", HTTP_HX_REQUEST="true"
        )
        self.assertContains(response, "Commissions")

    def test_detail_staff_context_has_daily_rate(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            f"/employees/user/{self.staff_user.id}/", HTTP_HX_REQUEST="true"
        )
        self.assertContains(response, "Daily Rate")
