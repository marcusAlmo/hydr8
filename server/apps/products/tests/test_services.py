"""Tests for apps.products.services — write-side business logic."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.models import Product
from apps.users.models import User, Role, DriverCommission
from apps.products.services import (
    activate_product,
    bulk_set_commission_rates,
    deactivate_product,
    delete_product,
    save_commission_matrix,
    set_commission_rate,
    update_product,
)


class UpdateProductTests(TestCase):
    """Tests for update_product — edit name/variation/price on non-default products."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
            first_name="Admin", last_name="User",
        )
        self.product = Product.objects.create(
            name="Test Water", variation="1L", price="20.00",
            is_default=False, category="WATER",
        )
        self.default_product = Product.objects.create(
            name="Alkaline Water", variation="5-Gallon Round", price="40.00",
            is_default=True, category="WATER",
        )

    def test_update_price(self):
        updated = update_product(
            product_id=self.product.id, performed_by=self.admin, price="25.50",
        )
        self.assertEqual(updated.price, Decimal("25.50"))

    def test_update_name(self):
        updated = update_product(
            product_id=self.product.id, performed_by=self.admin, name="Premium Water",
        )
        self.assertEqual(updated.name, "Premium Water")

    def test_update_variation(self):
        updated = update_product(
            product_id=self.product.id, performed_by=self.admin, variation="2L",
        )
        self.assertEqual(updated.variation, "2L")

    def test_default_product_cannot_be_edited(self):
        with self.assertRaises(ValidationError):
            update_product(
                product_id=self.default_product.id, performed_by=self.admin, price="99.00",
            )

    def test_nonexistent_product_raises(self):
        with self.assertRaises(ValidationError):
            update_product(product_id=99999, performed_by=self.admin, price="10.00")

    def test_negative_price_raises(self):
        with self.assertRaises(ValidationError):
            update_product(
                product_id=self.product.id, performed_by=self.admin, price="-5.00",
            )

    def test_empty_name_raises(self):
        with self.assertRaises(ValidationError):
            update_product(
                product_id=self.product.id, performed_by=self.admin, name="   ",
            )

    def test_no_fields_raises(self):
        with self.assertRaises(ValidationError):
            update_product(product_id=self.product.id, performed_by=self.admin)

    def test_duplicate_name_variation_raises(self):
        Product.objects.create(
            name="Existing", variation="1L", price="10.00",
            is_default=False, category="WATER",
        )
        with self.assertRaises(ValidationError):
            update_product(
                product_id=self.product.id, performed_by=self.admin,
                name="Existing", variation="1L",
            )


class ActivateDeactivateProductTests(TestCase):
    """Tests for activate_product and deactivate_product."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )
        self.product = Product.objects.create(
            name="Test Water", variation="1L", price="20.00",
            is_default=False, category="WATER",
        )

    def test_deactivate_sets_deactivated_at(self):
        result = deactivate_product(product_id=self.product.id, performed_by=self.admin)
        self.assertIsNotNone(result.deactivated_at)

    def test_activate_clears_deactivated_at(self):
        deactivate_product(product_id=self.product.id, performed_by=self.admin)
        result = activate_product(product_id=self.product.id, performed_by=self.admin)
        self.assertIsNone(result.deactivated_at)

    def test_deactivate_already_inactive_raises(self):
        deactivate_product(product_id=self.product.id, performed_by=self.admin)
        with self.assertRaises(ValidationError):
            deactivate_product(product_id=self.product.id, performed_by=self.admin)

    def test_activate_already_active_raises(self):
        with self.assertRaises(ValidationError):
            activate_product(product_id=self.product.id, performed_by=self.admin)


class DeleteProductTests(TestCase):
    """Tests for delete_product — soft-delete non-default products."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )
        self.product = Product.objects.create(
            name="Test Water", variation="1L", price="20.00",
            is_default=False, category="WATER",
        )
        self.default_product = Product.objects.create(
            name="Alkaline Water", variation="5-Gallon Round", price="40.00",
            is_default=True, category="WATER",
        )

    def test_delete_soft_deletes(self):
        result = delete_product(product_id=self.product.id, performed_by=self.admin)
        self.assertIsNotNone(result.deleted_at)
        # Should not appear in default queryset filters.
        self.assertFalse(
            Product.objects.filter(id=self.product.id, deleted_at__isnull=True).exists()
        )

    def test_default_product_cannot_be_deleted(self):
        with self.assertRaises(ValidationError):
            delete_product(
                product_id=self.default_product.id, performed_by=self.admin,
            )

    def test_nonexistent_product_raises(self):
        with self.assertRaises(ValidationError):
            delete_product(product_id=99999, performed_by=self.admin)


class SetCommissionRateTests(TestCase):
    """Tests for set_commission_rate — single driver×product upsert."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )
        self.driver_role = Role.objects.get_or_create(name="driver")[0]
        self.driver = User.objects.create_user(
            username="test.driver", password="pw1234567",
            first_name="Test", last_name="Driver", role=self.driver_role,
        )
        self.product = Product.objects.create(
            name="Test Water", variation="1L", price="20.00",
            is_default=False, category="WATER",
        )

    def test_create_new_rate(self):
        dc = set_commission_rate(
            driver_id=self.driver.id, product_id=self.product.id,
            rate="5.50", performed_by=self.admin,
        )
        self.assertEqual(dc.rate_per_unit, Decimal("5.50"))

    def test_update_existing_rate(self):
        set_commission_rate(
            driver_id=self.driver.id, product_id=self.product.id,
            rate="5.50", performed_by=self.admin,
        )
        dc = set_commission_rate(
            driver_id=self.driver.id, product_id=self.product.id,
            rate="7.25", performed_by=self.admin,
        )
        self.assertEqual(dc.rate_per_unit, Decimal("7.25"))
        self.assertEqual(DriverCommission.objects.count(), 1)

    def test_negative_rate_raises(self):
        with self.assertRaises(ValidationError):
            set_commission_rate(
                driver_id=self.driver.id, product_id=self.product.id,
                rate="-1.00", performed_by=self.admin,
            )

    def test_non_driver_raises(self):
        staff_role = Role.objects.get_or_create(name="staff")[0]
        staff = User.objects.create_user(
            username="test.staff", password="pw1234567",
            first_name="Test", last_name="Staff", role=staff_role,
        )
        with self.assertRaises(ValidationError):
            set_commission_rate(
                driver_id=staff.id, product_id=self.product.id,
                rate="5.00", performed_by=self.admin,
            )


class BulkSetCommissionRatesTests(TestCase):
    """Tests for bulk_set_commission_rates — set all drivers for a product."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )
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

    def test_bulk_set_creates_rows_for_all_drivers(self):
        count = bulk_set_commission_rates(
            product_id=self.product.id, rate="5.00", performed_by=self.admin,
        )
        self.assertEqual(count, 2)
        self.assertEqual(DriverCommission.objects.count(), 2)
        for dc in DriverCommission.objects.all():
            self.assertEqual(dc.rate_per_unit, Decimal("5.00"))

    def test_bulk_set_updates_existing_rows(self):
        set_commission_rate(
            driver_id=self.d1.id, product_id=self.product.id,
            rate="3.00", performed_by=self.admin,
        )
        count = bulk_set_commission_rates(
            product_id=self.product.id, rate="6.00", performed_by=self.admin,
        )
        self.assertEqual(count, 2)
        self.assertEqual(DriverCommission.objects.count(), 2)
        # d1 should be updated to 6.00
        dc = DriverCommission.objects.get(driver=self.d1, product=self.product)
        self.assertEqual(dc.rate_per_unit, Decimal("6.00"))


class SaveCommissionMatrixTests(TestCase):
    """Tests for save_commission_matrix — batch cell saves."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin", password="pw1234567",
        )
        self.driver_role = Role.objects.get_or_create(name="driver")[0]
        self.driver = User.objects.create_user(
            username="test.driver", password="pw1234567",
            first_name="Test", last_name="Driver", role=self.driver_role,
        )
        self.p1 = Product.objects.create(
            name="Water A", variation="1L", price="20.00",
            is_default=False, category="WATER",
        )
        self.p2 = Product.objects.create(
            name="Water B", variation="2L", price="30.00",
            is_default=False, category="WATER",
        )

    def test_save_multiple_cells(self):
        changes = {
            f"{self.driver.id}:{self.p1.id}": "5.00",
            f"{self.driver.id}:{self.p2.id}": "7.50",
        }
        count = save_commission_matrix(changes=changes, performed_by=self.admin)
        self.assertEqual(count, 2)
        self.assertEqual(DriverCommission.objects.count(), 2)

    def test_empty_changes_raises(self):
        with self.assertRaises(ValidationError):
            save_commission_matrix(changes={}, performed_by=self.admin)

    def test_invalid_key_format_raises(self):
        with self.assertRaises(ValidationError):
            save_commission_matrix(
                changes={"bad_key": "5.00"}, performed_by=self.admin,
            )


class TenantIsolationTests(TestCase):
    """Tests verifying that staff users can only mutate products and
    commissions within their own company (tenant)."""

    def setUp(self):
        from apps.settings.models import Company
        self.company_a = Company.objects.create(name="Company A")
        self.company_b = Company.objects.create(name="Company B")

        self.admin_a = User.objects.create_user(
            username="admin_a", password="pw1234567",
            is_staff=True, company=self.company_a,
        )
        self.admin_b = User.objects.create_user(
            username="admin_b", password="pw1234567",
            is_staff=True, company=self.company_b,
        )

        self.driver_role = Role.objects.get_or_create(name="driver")[0]
        self.driver_a = User.objects.create_user(
            username="driver_a", password="pw1234567",
            first_name="Driver", last_name="A",
            role=self.driver_role, company=self.company_a,
        )
        self.driver_b = User.objects.create_user(
            username="driver_b", password="pw1234567",
            first_name="Driver", last_name="B",
            role=self.driver_role, company=self.company_b,
        )

        self.product_a = Product.objects.create(
            name="Water A", variation="1L", price="20.00",
            is_default=False, category="WATER", company=self.company_a,
        )
        self.product_b = Product.objects.create(
            name="Water B", variation="1L", price="20.00",
            is_default=False, category="WATER", company=self.company_b,
        )

    def test_staff_cannot_edit_other_tenant_product(self):
        """Staff from company A cannot update a product in company B."""
        with self.assertRaises(ValidationError):
            update_product(
                product_id=self.product_b.id, performed_by=self.admin_a,
                price="99.00",
            )

    def test_staff_cannot_delete_other_tenant_product(self):
        with self.assertRaises(ValidationError):
            delete_product(
                product_id=self.product_b.id, performed_by=self.admin_a,
            )

    def test_staff_cannot_deactivate_other_tenant_product(self):
        with self.assertRaises(ValidationError):
            deactivate_product(
                product_id=self.product_b.id, performed_by=self.admin_a,
            )

    def test_staff_cannot_set_commission_for_other_tenant_driver(self):
        with self.assertRaises(ValidationError):
            set_commission_rate(
                driver_id=self.driver_b.id, product_id=self.product_a.id,
                rate="5.00", performed_by=self.admin_a,
            )

    def test_staff_cannot_bulk_set_other_tenant_drivers(self):
        """bulk_set_commission_rates should only affect the performer's
        own tenant drivers, not drivers in other companies."""
        count = bulk_set_commission_rates(
            product_id=self.product_a.id, rate="5.00",
            performed_by=self.admin_a,
        )
        # Only driver_a should be affected, not driver_b.
        self.assertEqual(count, 1)

    def test_superuser_can_access_all_tenants(self):
        """Superusers bypass tenant scoping."""
        result = update_product(
            product_id=self.product_b.id, performed_by=self.admin_a if self.admin_a.is_superuser else User.objects.create_superuser(
                username="super", password="pw1234567",
            ),
            price="99.00",
        )
        self.assertEqual(str(result.price), "99.00")

    def test_staff_can_edit_own_tenant_product(self):
        result = update_product(
            product_id=self.product_a.id, performed_by=self.admin_a,
            price="25.00",
        )
        self.assertEqual(str(result.price), "25.00")
