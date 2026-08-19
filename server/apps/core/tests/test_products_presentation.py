"""Tests for core.presentation_products — template-ready dict shaping.

Presentation functions take raw Product instances and rider data, then
shape them into the dicts consumed by products_pricing.html templates.
"""
from django.test import TestCase

from apps.core.models import Product
from apps.users.models import User, Role, DriverCommission
from apps.core.selectors_products import (
    get_commission_rates,
    list_active_products,
    list_products,
    list_riders,
)
from apps.core.presentation_products import (
    build_products_pricing_context,
    build_rate_map,
    product_column,
    product_row,
    rider_row,
    short_label,
)


class ShortLabelTests(TestCase):
    """Tests for short_label."""

    def test_extracts_first_word_and_size_token(self):
        self.assertEqual(
            short_label("Alkaline Water", "5-Gallon Round"),
            "Alkaline (5-Gallon)",
        )

    def test_no_variation_returns_base(self):
        self.assertEqual(short_label("Water", None), "Water")

    def test_empty_name_returns_question_mark(self):
        self.assertEqual(short_label("", None), "?")


class ProductRowTests(TestCase):
    """Tests for product_row — table row dict shaping."""

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

    def test_active_product_row(self):
        row = product_row(self.active)
        self.assertEqual(row["id"], self.active.id)
        self.assertEqual(row["name"], "Alkaline Water")
        self.assertEqual(row["unit_price"], "40.00")
        self.assertTrue(row["is_active"])
        self.assertTrue(row["is_default"])
        self.assertFalse(row["action_activate"])
        self.assertEqual(row["row_class"], "")
        self.assertEqual(row["name_class"], "text-on-surface")

    def test_inactive_product_row(self):
        row = product_row(self.inactive)
        self.assertFalse(row["is_active"])
        self.assertTrue(row["action_activate"])
        self.assertEqual(row["row_class"], "bg-surface-container-low/50")
        self.assertEqual(row["name_class"], "text-on-surface-variant")


class ProductColumnTests(TestCase):
    """Tests for product_column — commission matrix column header dict."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )
        self.product = Product.objects.create(
            name="Alkaline Water", variation="5-Gallon Round", price="40.00",
            is_default=True, category="WATER",
        )

    def test_column_has_label_and_border_class(self):
        col = product_column(self.product, 0)
        self.assertEqual(col["id"], self.product.id)
        self.assertIn("label", col)
        self.assertTrue(col["border_class"].startswith("border-b-4"))


class RiderRowTests(TestCase):
    """Tests for rider_row — commission matrix row dict shaping."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )
        self.driver_role = Role.objects.get_or_create(name="driver")[0]
        self.driver = User.objects.create_user(
            username="test.driver", password="pw1234567",
            first_name="Juan", last_name="Cruz", role=self.driver_role,
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

    def test_rider_row_has_required_fields(self):
        product_ids = [self.p1.id, self.p2.id]
        rate_map = build_rate_map(
            get_commission_rates([self.driver], product_ids)
        )
        row = rider_row(self.driver, product_ids, rate_map)
        self.assertEqual(row["id"], str(self.driver.pk))
        self.assertEqual(row["name"], "Juan Cruz")
        self.assertEqual(row["initials"], "JC")
        self.assertTrue(row["driver_code"].startswith("DRV-"))
        self.assertTrue(row["avatar_bg"].startswith("bg-"))
        self.assertTrue(row["avatar_text"].startswith("text-"))

    def test_rate_cells_aligned_to_products(self):
        product_ids = [self.p1.id, self.p2.id]
        rate_map = build_rate_map(
            get_commission_rates([self.driver], product_ids)
        )
        row = rider_row(self.driver, product_ids, rate_map)
        self.assertEqual(len(row["rate_cells"]), 2)
        cell_p1 = next(c for c in row["rate_cells"] if c["product_id"] == self.p1.id)
        cell_p2 = next(c for c in row["rate_cells"] if c["product_id"] == self.p2.id)
        self.assertEqual(cell_p1["rate"], "5.50")
        self.assertEqual(cell_p2["rate"], "0.00")


class BuildProductsPricingContextTests(TestCase):
    """Tests for build_products_pricing_context — full page context assembly."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )

    def test_context_has_required_keys(self):
        ctx = build_products_pricing_context(
            products=[], columns=[], riders=[],
        )
        for key in (
            "today_date", "tabs", "products", "active_count",
            "default_count", "total_count",
            "product_columns", "page_size", "rider_count", "riders",
        ):
            self.assertIn(key, ctx, f"Missing key: {key}")

    def test_tabs_have_correct_ids(self):
        ctx = build_products_pricing_context(
            products=[], columns=[], riders=[],
        )
        tab_ids = [t["id"] for t in ctx["tabs"]]
        self.assertEqual(tab_ids, ["products", "commissions"])

    def test_counts_are_consistent(self):
        p1 = Product.objects.create(
            name="A", variation="1L", price="10.00",
            is_default=True, category="WATER",
        )
        p2 = Product.objects.create(
            name="B", variation="1L", price="10.00",
            is_default=False, category="WATER",
        )
        products = [product_row(p) for p in [p1, p2]]
        ctx = build_products_pricing_context(
            products=products, columns=[], riders=[],
        )
        self.assertEqual(ctx["total_count"], 2)
        self.assertEqual(ctx["default_count"], 1)
        self.assertEqual(ctx["active_count"], 2)
