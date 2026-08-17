"""Tests for apps.employees.selectors — read-side query logic."""
from django.test import TestCase

from apps.employees.selectors import (
    get_employee_directory_context,
    get_roles_permissions_context,
    get_user_detail_context,
)
from apps.users.models import Role, User


class GetEmployeeDirectoryContextTests(TestCase):
    """Tests for get_employee_directory_context."""

    def setUp(self):
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.staff_role, _ = Role.objects.get_or_create(name="Staff")
        self.driver_role, _ = Role.objects.get_or_create(name="Driver")

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
        self.driver.role = self.driver_role
        self.driver.save()

    def test_returns_context_with_users(self):
        ctx = get_employee_directory_context(self.admin)
        self.assertIn("users", ctx)
        self.assertIn("stats", ctx)
        self.assertIn("filters", ctx)
        self.assertIn("pagination", ctx)

    def test_includes_all_active_users(self):
        ctx = get_employee_directory_context(self.admin)
        usernames = [u["username"] for u in ctx["users"]]
        self.assertIn("@admin", usernames)
        self.assertIn("@driver1", usernames)

    def test_search_filters_by_first_name(self):
        ctx = get_employee_directory_context(self.admin, query="Dave")
        usernames = [u["username"] for u in ctx["users"]]
        self.assertIn("@driver1", usernames)
        self.assertNotIn("@admin", usernames)

    def test_search_is_case_insensitive(self):
        ctx = get_employee_directory_context(self.admin, query="alice")
        usernames = [u["username"] for u in ctx["users"]]
        self.assertIn("@admin", usernames)

    def test_stats_count_active_users(self):
        ctx = get_employee_directory_context(self.admin)
        stat_keys = {s["key"]: s["raw_value"] for s in ctx["stats"]}
        # admin + driver are both active
        self.assertEqual(stat_keys["active_users"], 2)
        self.assertEqual(stat_keys["active_riders"], 1)

    def test_excludes_soft_deleted_users(self):
        self.driver.deleted_at = "2026-01-01T00:00:00Z"
        self.driver.save()
        ctx = get_employee_directory_context(self.admin)
        usernames = [u["username"] for u in ctx["users"]]
        self.assertNotIn("@driver1", usernames)

    def test_pagination_returns_valid_dict(self):
        ctx = get_employee_directory_context(self.admin, page=1)
        pag = ctx["pagination"]
        self.assertIn("total", pag)
        self.assertIn("current_page", pag)
        self.assertEqual(pag["current_page"], 1)


class GetRolesPermissionsContextTests(TestCase):
    """Tests for get_roles_permissions_context."""

    def setUp(self):
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.admin = User.objects.create_user(
            username="admin", password="pw1234567",
        )
        self.admin.role = self.admin_role
        self.admin.save()

    def test_returns_modules_and_roles(self):
        ctx = get_roles_permissions_context(self.admin)
        self.assertIn("modules", ctx)
        self.assertIn("roles", ctx)
        self.assertIsInstance(ctx["modules"], list)
        self.assertIsInstance(ctx["roles"], list)

    def test_includes_three_default_roles(self):
        ctx = get_roles_permissions_context(self.admin)
        role_names = [r["name"] for r in ctx["roles"]]
        self.assertIn("Admin", role_names)
        self.assertIn("Staff", role_names)
        self.assertIn("Driver", role_names)

    def test_role_has_permission_rows(self):
        ctx = get_roles_permissions_context(self.admin)
        for role in ctx["roles"]:
            self.assertIn("permissions", role)
            self.assertEqual(len(role["permissions"]), len(ctx["modules"]))


class GetUserDetailContextTests(TestCase):
    """Tests for get_user_detail_context."""

    def setUp(self):
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.staff_role, _ = Role.objects.get_or_create(name="Staff")
        self.driver_role, _ = Role.objects.get_or_create(name="Driver")

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

    def test_returns_none_for_missing_user(self):
        ctx = get_user_detail_context(self.admin, "00000000-0000-0000-0000-000000000000")
        self.assertIsNone(ctx)

    def test_driver_context_has_driver_stats(self):
        ctx = get_user_detail_context(self.admin, str(self.driver.id))
        self.assertIsNotNone(ctx)
        self.assertTrue(ctx.get("is_driver"))
        self.assertIn("driver_stats", ctx)

    def test_staff_context_has_staff_stats(self):
        ctx = get_user_detail_context(self.admin, str(self.staff_user.id))
        self.assertIsNotNone(ctx)
        self.assertTrue(ctx.get("is_staff"))
        self.assertIn("staff_stats", ctx)

    def test_admin_context_is_admin(self):
        ctx = get_user_detail_context(self.admin, str(self.admin.id))
        self.assertIsNotNone(ctx)
        self.assertTrue(ctx.get("is_admin"))

    def test_profile_has_user_uuid(self):
        ctx = get_user_detail_context(self.admin, str(self.driver.id))
        self.assertEqual(ctx["profile"]["user_uuid"], str(self.driver.id))
