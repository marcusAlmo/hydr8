"""Tests for apps.users.selectors_employees — read-side query logic."""
from django.test import TestCase

from apps.users.selectors_employees import (
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

    def test_driver_debts_handled_pulls_from_credit_lines(self):
        """Outstanding debts handled by a driver come from CreditLine
        records attributed via ``care_of`` (the Customers "Record Debt"
        modal), not the legacy RiderCredit table."""
        from decimal import Decimal

        from apps.core.models import Product
        from apps.customers.models import CreditLine, Customer

        customer = Customer.objects.create(name="Debt Test Store")
        product = Product.objects.create(
            name="Alkaline", variation="Round", price=Decimal("40.00"),
        )
        CreditLine.objects.create(
            customer=customer,
            product=product,
            qty_credited=5,
            qty_remaining=3,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("200.00"),
            care_of=self.driver,
        )

        ctx = get_user_detail_context(self.admin, str(self.driver.id))
        debts = ctx["debts_handled"]
        self.assertEqual(len(debts), 1)
        self.assertEqual(debts[0]["customer_name"], "Debt Test Store")
        # Outstanding = 3 remaining * 40.00 = 120.00
        self.assertEqual(debts[0]["amount_raw"], 120.0)
        # The stat card subtitle should reflect 1 customer.
        debts_stat = next(
            s for s in ctx["driver_stats"] if s["key"] == "debts_outstanding"
        )
        self.assertEqual(debts_stat["raw_value"], 120.0)

    def _make_credit_line(self, *, customer, product, care_of, qty_remaining,
                          unit_price="40.00", days_ago=0):
        """Helper: create a CreditLine with the given outstanding balance."""
        from datetime import timedelta
        from decimal import Decimal

        from django.utils import timezone

        from apps.customers.models import CreditLine

        qty_credited = max(qty_remaining, 1)
        return CreditLine.objects.create(
            customer=customer,
            product=product,
            qty_credited=qty_credited,
            qty_remaining=qty_remaining,
            unit_price_snapshot=Decimal(unit_price),
            total_credit_amount=Decimal(unit_price) * qty_credited,
            care_of=care_of,
            transaction_date=timezone.localdate() - timedelta(days=days_ago),
        )

    def test_driver_debts_excludes_repaid_lines(self):
        """A CreditLine with qty_remaining=0 must not appear in debts_handled."""
        from decimal import Decimal

        from apps.core.models import Product
        from apps.customers.models import Customer

        customer = Customer.objects.create(name="Repaid Store")
        product = Product.objects.create(
            name="Alkaline", variation="Round", price=Decimal("40.00"),
        )
        # Fully repaid line — should be excluded.
        self._make_credit_line(
            customer=customer, product=product,
            care_of=self.driver, qty_remaining=0,
        )

        ctx = get_user_detail_context(self.admin, str(self.driver.id))
        self.assertEqual(ctx["debts_handled"], [])
        debts_stat = next(
            s for s in ctx["driver_stats"] if s["key"] == "debts_outstanding"
        )
        self.assertEqual(debts_stat["raw_value"], 0.0)

    def test_driver_debts_excludes_lines_for_other_drivers(self):
        """Only lines whose ``care_of`` matches the viewed driver are included."""
        from decimal import Decimal

        from apps.core.models import Product
        from apps.customers.models import Customer
        from apps.users.models import User

        other = User.objects.create_user(
            username="driver2", password="pw1234567",
            first_name="Dana", last_name="Driver",
        )
        other.role = self.driver_role
        other.save()

        customer = Customer.objects.create(name="Other Driver Store")
        product = Product.objects.create(
            name="Alkaline", variation="Round", price=Decimal("40.00"),
        )
        # Attributed to *another* driver — must not appear for self.driver.
        self._make_credit_line(
            customer=customer, product=product,
            care_of=other, qty_remaining=2,
        )

        ctx = get_user_detail_context(self.admin, str(self.driver.id))
        self.assertEqual(ctx["debts_handled"], [])

    def test_driver_debts_overdue_boundary_at_eight_days(self):
        """Lines older than 7 days are labelled 'Overdue'; <=7 days are 'Pending'."""
        from decimal import Decimal

        from apps.core.models import Product
        from apps.customers.models import Customer

        customer = Customer.objects.create(name="Boundary Store")
        product = Product.objects.create(
            name="Alkaline", variation="Round", price=Decimal("40.00"),
        )
        # 8 days old → overdue
        self._make_credit_line(
            customer=customer, product=product,
            care_of=self.driver, qty_remaining=1, days_ago=8,
        )
        # 7 days old → pending
        self._make_credit_line(
            customer=customer, product=product,
            care_of=self.driver, qty_remaining=1, days_ago=7,
        )

        ctx = get_user_detail_context(self.admin, str(self.driver.id))
        debts = sorted(ctx["debts_handled"], key=lambda d: d["days_overdue"])
        self.assertEqual(len(debts), 2)
        self.assertEqual(debts[0]["status"], "pending")
        self.assertEqual(debts[0]["status_label"], "Pending")
        self.assertEqual(debts[1]["status"], "overdue")
        self.assertEqual(debts[1]["status_label"], "Overdue")

    def test_driver_debts_subtitle_counts_distinct_customers(self):
        """When one customer has multiple open lines, the subtitle reports
        1 customer (not 2) but 2 open debts."""
        from decimal import Decimal

        from apps.core.models import Product
        from apps.customers.models import Customer

        customer = Customer.objects.create(name="Multi Line Store")
        product = Product.objects.create(
            name="Alkaline", variation="Round", price=Decimal("40.00"),
        )
        self._make_credit_line(
            customer=customer, product=product,
            care_of=self.driver, qty_remaining=2,
        )
        self._make_credit_line(
            customer=customer, product=product,
            care_of=self.driver, qty_remaining=1,
        )

        ctx = get_user_detail_context(self.admin, str(self.driver.id))
        self.assertEqual(len(ctx["debts_handled"]), 2)
        debts_stat = next(
            s for s in ctx["driver_stats"] if s["key"] == "debts_outstanding"
        )
        # Subtitle should mention "1 customer, 2 open debts"
        self.assertIn("1 customer,", debts_stat["subtitle"])
        self.assertIn("2 open debts", debts_stat["subtitle"])
        # Total = (2*40) + (1*40) = 120
        self.assertEqual(debts_stat["raw_value"], 120.0)
