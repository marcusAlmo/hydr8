"""Tests for apps.products.selectors — read-side query logic."""
from django.test import TestCase

from apps.core.models import Product
from apps.users.models import User, Role, DriverCommission
from apps.products.selectors import (
    get_products_pricing_context,
    list_product_columns,
    list_products,
    list_riders_with_rates,
)


class ListProductsTests(TestCase):
    """Tests for list_products — product catalogue rows for the Products tab."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )
        self.active_default = Product.objects.create(
            name="Alkaline Water", variation="5-Gallon Round", price="40.00",
            is_default=True, category="WATER",
        )
        self.active_custom = Product.objects.create(
            name="Custom Water", variation="1L", price="15.00",
            is_default=False, category="WATER",
        )
        self.inactive_custom = Product.objects.create(
            name="Old Water", variation="2L", price="10.00",
            is_default=False, category="WATER", deactivated_at="2026-01-01T00:00:00Z",
        )
        self.deleted = Product.objects.create(
            name="Deleted Water", variation="3L", price="5.00",
            is_default=False, category="WATER", deleted_at="2026-01-01T00:00:00Z",
        )

    def test_excludes_soft_deleted(self):
        rows = list_products(self.admin)
        ids = [r["id"] for r in rows]
        self.assertNotIn(self.deleted.id, ids)

    def test_includes_inactive_products(self):
        """Inactive products should appear so admins can re-activate them."""
        rows = list_products(self.admin)
        ids = [r["id"] for r in rows]
        self.assertIn(self.inactive_custom.id, ids)

    def test_active_flag_correct(self):
        rows = list_products(self.admin)
        by_id = {r["id"]: r for r in rows}
        self.assertTrue(by_id[self.active_default.id]["is_active"])
        self.assertFalse(by_id[self.inactive_custom.id]["is_active"])

    def test_action_activate_only_for_inactive(self):
        rows = list_products(self.admin)
        by_id = {r["id"]: r for r in rows}
        self.assertFalse(by_id[self.active_default.id]["action_activate"])
        self.assertTrue(by_id[self.inactive_custom.id]["action_activate"])

    def test_is_default_flag_correct(self):
        rows = list_products(self.admin)
        by_id = {r["id"]: r for r in rows}
        self.assertTrue(by_id[self.active_default.id]["is_default"])
        self.assertFalse(by_id[self.active_custom.id]["is_default"])

    def test_unit_price_formatted_as_string(self):
        rows = list_products(self.admin)
        by_id = {r["id"]: r for r in rows}
        self.assertEqual(by_id[self.active_default.id]["unit_price"], "40.00")

    def test_empty_db_returns_empty_list(self):
        Product.objects.all().delete()
        rows = list_products(self.admin)
        self.assertEqual(rows, [])


class ListProductColumnsTests(TestCase):
    """Tests for list_product_columns — active products as matrix columns."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )
        self.active = Product.objects.create(
            name="Alkaline Water", variation="5-Gallon Round", price="40.00",
            is_default=True, category="WATER",
        )
        self.inactive = Product.objects.create(
            name="Old Water", variation="2L", price="10.00",
            is_default=False, category="WATER", deactivated_at="2026-01-01T00:00:00Z",
        )
        self.deleted = Product.objects.create(
            name="Deleted Water", variation="3L", price="5.00",
            is_default=False, category="WATER", deleted_at="2026-01-01T00:00:00Z",
        )

    def test_excludes_inactive_and_deleted(self):
        cols = list_product_columns(self.admin)
        ids = [c["id"] for c in cols]
        self.assertIn(self.active.id, ids)
        self.assertNotIn(self.inactive.id, ids)
        self.assertNotIn(self.deleted.id, ids)

    def test_column_has_label_and_border_class(self):
        cols = list_product_columns(self.admin)
        col = cols[0]
        self.assertIn("label", col)
        self.assertIn("border_class", col)
        self.assertTrue(col["border_class"].startswith("border-b-4"))


class ListRidersWithRatesTests(TestCase):
    """Tests for list_riders_with_rates — driver rows for the matrix."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )
        self.driver_role = Role.objects.get_or_create(name="driver")[0]
        self.staff_role = Role.objects.get_or_create(name="staff")[0]
        self.driver = User.objects.create_user(
            username="test.driver", password="pw1234567",
            first_name="Juan", last_name="Cruz", role=self.driver_role,
        )
        # Non-driver should NOT appear in the rider list.
        self.staff = User.objects.create_user(
            username="test.staff", password="pw1234567",
            first_name="Maria", last_name="Staff", role=self.staff_role,
        )
        self.p1 = Product.objects.create(
            name="Alkaline Water", variation="5-Gallon Round", price="40.00",
            is_default=True, category="WATER",
        )
        self.p2 = Product.objects.create(
            name="Mineral Water", variation="5-Gallon Slim", price="35.00",
            is_default=True, category="WATER",
        )
        DriverCommission.objects.create(
            driver=self.driver, product=self.p1, rate_per_unit="5.50",
        )

    def test_returns_only_drivers(self):
        rows = list_riders_with_rates(self.admin)
        ids = [r["id"] for r in rows]
        self.assertIn(str(self.driver.pk), ids)
        self.assertNotIn(str(self.staff.pk), ids)

    def test_rate_cells_aligned_to_product_columns(self):
        rows = list_riders_with_rates(self.admin)
        rider = next(r for r in rows if r["id"] == str(self.driver.pk))
        # Should have one cell per active product column.
        self.assertEqual(len(rider["rate_cells"]), 2)
        # p1 has a rate; p2 defaults to "0.00".
        cell_p1 = next(c for c in rider["rate_cells"] if c["product_id"] == self.p1.id)
        cell_p2 = next(c for c in rider["rate_cells"] if c["product_id"] == self.p2.id)
        self.assertEqual(cell_p1["rate"], "5.50")
        self.assertEqual(cell_p2["rate"], "0.00")

    def test_initials_derived_from_name(self):
        rows = list_riders_with_rates(self.admin)
        rider = next(r for r in rows if r["id"] == str(self.driver.pk))
        self.assertEqual(rider["initials"], "JC")

    def test_driver_code_uses_pk(self):
        rows = list_riders_with_rates(self.admin)
        rider = next(r for r in rows if r["id"] == str(self.driver.pk))
        self.assertTrue(rider["driver_code"].startswith("DRV-"))

    def test_avatar_classes_are_strings(self):
        rows = list_riders_with_rates(self.admin)
        rider = next(r for r in rows if r["id"] == str(self.driver.pk))
        self.assertTrue(rider["avatar_bg"].startswith("bg-"))
        self.assertTrue(rider["avatar_text"].startswith("text-"))


class GetProductsPricingContextTests(TestCase):
    """Tests for get_products_pricing_context — full page context assembly."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )

    def test_context_has_required_keys(self):
        ctx = get_products_pricing_context(self.admin)
        for key in (
            "today_date", "tabs", "products", "active_count",
            "default_count", "total_count", "ai_insight",
            "product_columns", "page_size", "rider_count", "riders",
        ):
            self.assertIn(key, ctx, f"Missing key: {key}")

    def test_tabs_have_correct_ids(self):
        ctx = get_products_pricing_context(self.admin)
        tab_ids = [t["id"] for t in ctx["tabs"]]
        self.assertEqual(tab_ids, ["products", "commissions"])

    def test_counts_are_consistent(self):
        Product.objects.create(
            name="A", variation="1L", price="10.00",
            is_default=True, category="WATER",
        )
        Product.objects.create(
            name="B", variation="1L", price="10.00",
            is_default=False, category="WATER",
        )
        ctx = get_products_pricing_context(self.admin)
        self.assertEqual(ctx["total_count"], 2)
        self.assertEqual(ctx["default_count"], 1)
        self.assertEqual(ctx["active_count"], 2)
