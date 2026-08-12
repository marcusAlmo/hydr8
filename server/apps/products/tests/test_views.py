"""Tests for apps.products.views — HTTP endpoints for the Products & Pricing page."""
import json

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import Product
from apps.users.models import User, Role, DriverCommission


class ProductsPricingViewTests(TestCase):
    """Tests for the main page render — GET /products/."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="staff", password="pw1234567",
        )
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_page_renders_200(self):
        response = self.client.get("/products/")
        self.assertEqual(response.status_code, 200)

    def test_page_contains_product_inventory_heading(self):
        Product.objects.create(
            name="Test Water", variation="1L", price="10.00",
            is_default=False, category="WATER",
        )
        response = self.client.get("/products/")
        self.assertContains(response, "Product Inventory")

    def test_page_contains_commission_matrix_heading(self):
        response = self.client.get("/products/")
        self.assertContains(response, "Commission Matrix")

    def test_page_contains_save_url(self):
        response = self.client.get("/products/")
        self.assertContains(response, "/products/save")

    def test_page_contains_commission_save_url(self):
        response = self.client.get("/products/")
        self.assertContains(response, "commission/save")

    def test_page_contains_commission_bulk_set_url(self):
        response = self.client.get("/products/")
        self.assertContains(response, "commission/bulk-set")

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get("/products/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("next", response.url)

    def test_rejects_non_get_methods(self):
        response = self.client.post("/products/")
        self.assertEqual(response.status_code, 405)


class VerifyPinViewTests(TestCase):
    """Tests for the PIN verification endpoint — POST /products/verify-pin/."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="staff", password="pw1234567",
        )
        self.user.set_pin("1234")
        self.user.save()
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_correct_pin_returns_verified_true(self):
        response = self.client.post(
            "/products/verify-pin/",
            data=json.dumps({"pin": "1234"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["verified"])

    def test_wrong_pin_returns_verified_false(self):
        response = self.client.post(
            "/products/verify-pin/",
            data=json.dumps({"pin": "9999"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["verified"])

    def test_missing_pin_returns_400(self):
        response = self.client.post(
            "/products/verify-pin/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_json_returns_400(self):
        response = self.client.post(
            "/products/verify-pin/",
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.post(
            "/products/verify-pin/",
            data=json.dumps({"pin": "1234"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)


class ProductsSaveViewTests(TestCase):
    """Tests for the product catalogue save endpoint — POST /products/save/."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )
        self.admin.set_pin("1234")
        self.admin.save()
        self.driver_role = Role.objects.get_or_create(name="driver")[0]
        self.driver = User.objects.create_user(
            username="driver", password="pw1234567",
            first_name="Test", last_name="Driver", role=self.driver_role,
        )
        self.product = Product.objects.create(
            name="Custom Water", variation="1L", price="20.00",
            is_default=False, category="WATER",
        )
        self.default_product = Product.objects.create(
            name="Alkaline Water", variation="5-Gallon Round", price="40.00",
            is_default=True, category="WATER",
        )
        cache.clear()
        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    def test_save_edit_with_correct_pin(self):
        response = self.client.post(
            "/products/save/",
            data=json.dumps({
                "pin": "1234",
                "edits": [{"id": self.product.id, "price": "25.00"}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["saved"], 1)
        self.product.refresh_from_db()
        self.assertEqual(str(self.product.price), "25.00")

    def test_save_with_wrong_pin_returns_403(self):
        response = self.client.post(
            "/products/save/",
            data=json.dumps({
                "pin": "9999",
                "edits": [{"id": self.product.id, "price": "25.00"}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data["ok"])

    def test_save_without_pin_returns_400(self):
        response = self.client.post(
            "/products/save/",
            data=json.dumps({
                "edits": [{"id": self.product.id, "price": "25.00"}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_driver_cannot_save(self):
        """Drivers (non-staff) should get 403."""
        self.client.logout()
        self.client.force_login(self.driver)
        response = self.client.post(
            "/products/save/",
            data=json.dumps({
                "pin": "1234",
                "edits": [{"id": self.product.id, "price": "25.00"}],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_save_delete(self):
        response = self.client.post(
            "/products/save/",
            data=json.dumps({
                "pin": "1234",
                "deletes": [self.product.id],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["deleted"], 1)
        self.product.refresh_from_db()
        self.assertIsNotNone(self.product.deleted_at)

    def test_save_activate(self):
        # Deactivate first
        from django.utils import timezone
        self.product.deactivated_at = timezone.now()
        self.product.save()
        response = self.client.post(
            "/products/save/",
            data=json.dumps({
                "pin": "1234",
                "activates": [self.product.id],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["activated"], 1)
        self.product.refresh_from_db()
        self.assertIsNone(self.product.deactivated_at)

    def test_save_no_changes_returns_400(self):
        response = self.client.post(
            "/products/save/",
            data=json.dumps({"pin": "1234"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.post(
            "/products/save/",
            data=json.dumps({"pin": "1234", "edits": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)


class CommissionSaveViewTests(TestCase):
    """Tests for the commission matrix save endpoint — POST /products/commission/save/."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )
        self.admin.set_pin("1234")
        self.admin.save()
        self.driver_role = Role.objects.get_or_create(name="driver")[0]
        self.driver = User.objects.create_user(
            username="driver", password="pw1234567",
            first_name="Test", last_name="Driver", role=self.driver_role,
        )
        self.product = Product.objects.create(
            name="Test Water", variation="1L", price="20.00",
            is_default=False, category="WATER",
        )
        cache.clear()
        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    def test_save_with_correct_pin(self):
        response = self.client.post(
            "/products/commission/save/",
            data=json.dumps({
                "pin": "1234",
                "changes": {f"{self.driver.id}:{self.product.id}": "5.50"},
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["saved"], 1)
        dc = DriverCommission.objects.get(driver=self.driver, product=self.product)
        self.assertEqual(str(dc.rate_per_unit), "5.50")

    def test_save_with_wrong_pin_returns_403(self):
        response = self.client.post(
            "/products/commission/save/",
            data=json.dumps({
                "pin": "9999",
                "changes": {f"{self.driver.id}:{self.product.id}": "5.50"},
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_save_empty_changes_returns_400(self):
        response = self.client.post(
            "/products/commission/save/",
            data=json.dumps({"pin": "1234", "changes": {}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_driver_cannot_save(self):
        self.client.logout()
        self.client.force_login(self.driver)
        response = self.client.post(
            "/products/commission/save/",
            data=json.dumps({
                "pin": "1234",
                "changes": {f"{self.driver.id}:{self.product.id}": "5.50"},
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)


class CommissionBulkSetViewTests(TestCase):
    """Tests for the commission bulk-set endpoint — POST /products/commission/bulk-set/."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )
        self.admin.set_pin("1234")
        self.admin.save()
        self.driver_role = Role.objects.get_or_create(name="driver")[0]
        self.d1 = User.objects.create_user(
            username="d1", password="pw1234567",
            first_name="Driver", last_name="One", role=self.driver_role,
        )
        self.d2 = User.objects.create_user(
            username="d2", password="pw1234567",
            first_name="Driver", last_name="Two", role=self.driver_role,
        )
        self.product = Product.objects.create(
            name="Test Water", variation="1L", price="20.00",
            is_default=False, category="WATER",
        )
        cache.clear()
        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    def test_bulk_set_with_correct_pin(self):
        response = self.client.post(
            "/products/commission/bulk-set/",
            data=json.dumps({
                "pin": "1234",
                "product_id": self.product.id,
                "rate": "5.00",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["updated"], 2)

    def test_bulk_set_with_wrong_pin_returns_403(self):
        response = self.client.post(
            "/products/commission/bulk-set/",
            data=json.dumps({
                "pin": "9999",
                "product_id": self.product.id,
                "rate": "5.00",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_bulk_set_missing_product_id_returns_400(self):
        response = self.client.post(
            "/products/commission/bulk-set/",
            data=json.dumps({"pin": "1234", "rate": "5.00"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
