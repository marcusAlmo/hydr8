"""Tests for core.selectors_products — read-side query logic.

Selectors return raw Product instances and rider querysets. Presentation
shaping (dict formatting, CSS classes, labels) is tested in
test_products_presentation.py.
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


class ListProductsTests(TestCase):
    """Tests for list_products — raw Product queryset for the Products tab."""

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
        products = list_products(self.admin)
        ids = [p.id for p in products]
        self.assertNotIn(self.deleted.id, ids)

    def test_includes_inactive_products(self):
        """Inactive products should appear so admins can re-activate them."""
        products = list_products(self.admin)
        ids = [p.id for p in products]
        self.assertIn(self.inactive_custom.id, ids)

    def test_returns_product_instances(self):
        products = list_products(self.admin)
        self.assertTrue(all(isinstance(p, Product) for p in products))

    def test_empty_db_returns_empty_list(self):
        Product.objects.all().delete()
        products = list_products(self.admin)
        self.assertEqual(products, [])


class ListActiveProductsTests(TestCase):
    """Tests for list_active_products — active products for commission columns."""

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
        products = list_active_products(self.admin)
        ids = [p.id for p in products]
        self.assertIn(self.active.id, ids)
        self.assertNotIn(self.inactive.id, ids)
        self.assertNotIn(self.deleted.id, ids)


class ListRidersTests(TestCase):
    """Tests for list_riders — driver queryset for the commission matrix."""

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
        self.staff = User.objects.create_user(
            username="test.staff", password="pw1234567",
            first_name="Maria", last_name="Staff", role=self.staff_role,
        )

    def test_returns_only_drivers(self):
        riders = list_riders(self.admin)
        ids = [r.pk for r in riders]
        self.assertIn(self.driver.pk, ids)
        self.assertNotIn(self.staff.pk, ids)

    def test_returns_user_instances(self):
        riders = list_riders(self.admin)
        self.assertTrue(all(isinstance(r, User) for r in riders))


class GetCommissionRatesTests(TestCase):
    """Tests for get_commission_rates — raw rate values."""

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

    def test_returns_rates_for_specified_products(self):
        riders = [self.driver]
        product_ids = [self.p1.id, self.p2.id]
        rates = get_commission_rates(riders, product_ids)
        self.assertEqual(len(rates), 1)
        self.assertEqual(rates[0]["driver_id"], self.driver.pk)
        self.assertEqual(rates[0]["product_id"], self.p1.id)

    def test_returns_empty_when_no_riders(self):
        rates = get_commission_rates([], [self.p1.id])
        self.assertEqual(rates, [])

    def test_returns_empty_when_no_products(self):
        rates = get_commission_rates([self.driver], [])
        self.assertEqual(rates, [])
