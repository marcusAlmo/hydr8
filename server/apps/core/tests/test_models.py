from django.test import SimpleTestCase, TestCase

from apps.core.models import Product, SystemConfig
from apps.tests.fakes import FakeProductRepository


class ProductModelTests(SimpleTestCase):
    def test_product_str(self):
        """Test Product string representation."""
        product = Product(name="Gallon Water", variation="8 Gal Round", price=50.00)
        self.assertEqual(str(product), "Gallon Water - 8 Gal Round")

    def test_product_defaults(self):
        """Test Product default values."""
        product = Product(name="Gallon Water", variation="Slim", price=45.00)
        self.assertTrue(product.is_active)

    def test_fake_product_repository(self):
        """Test FakeProductRepository operations without DB."""
        repo = FakeProductRepository()
        prod = repo.create_product(name="Mineral Water", variation="Standard", price=30.0)

        self.assertEqual(prod['id'], 1)
        self.assertEqual(prod['price'], 30.0)
        self.assertTrue(prod['is_active'])

        active_products = repo.filter(is_active=True)
        self.assertEqual(len(active_products), 1)


class SystemConfigModelTests(TestCase):
    def test_system_config_str(self):
        """Test SystemConfig string representation."""
        config = SystemConfig(key="TITHE_RATE", value="0.10")
        self.assertEqual(str(config), "TITHE_RATE: 0.10")

    def test_system_config_manager_get_value_existing(self):
        """Test SystemConfigManager.get_value retrieves value when present."""
        SystemConfig.objects.create(key="TITHE_RATE", value="0.10")
        value = SystemConfig.objects.get_value("TITHE_RATE")
        self.assertEqual(value, "0.10")

    def test_system_config_manager_get_value_default(self):
        """Test SystemConfigManager.get_value returns default when missing."""
        value = SystemConfig.objects.get_value("NON_EXISTENT_KEY", default="0.05")
        self.assertEqual(value, "0.05")
