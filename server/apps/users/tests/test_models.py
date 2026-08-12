from django.test import SimpleTestCase
from unittest.mock import patch
from apps.users.models import User, Role, Permission, DriverCommission
from apps.core.models import Product
from apps.tests.fakes import FakeUserRepository, FakeRoleRepository, FakePermissionRepository


class UserModelTests(SimpleTestCase):
    def test_user_initial_state(self):
        """Test that a user starts with default active status using SimpleTestCase."""
        user = User(username="testuser", email="testuser@example.com")
        self.assertTrue(user.is_active)
        self.assertIsNone(user.deleted_at)

    def test_user_name_property_returns_full_name(self):
        """Test name property returns first + last name when set."""
        user = User(username="johndoe", first_name="John", last_name="Doe")
        self.assertEqual(user.name, "John Doe")
        self.assertEqual(user.full_name, "John Doe")

    def test_user_name_property_falls_back_to_username(self):
        """Test name property falls back to username when first/last name are empty."""
        user = User(username="johndoe")
        self.assertEqual(user.name, "johndoe")
        self.assertEqual(user.full_name, "johndoe")

    def test_user_name_properties_with_single_name(self):
        """Test full_name and short_name fall back to username when only one of first_name/last_name is provided per schema requirement."""
        user_first = User(username="johndoe", first_name="John")
        self.assertEqual(user_first.full_name, "johndoe")
        self.assertEqual(user_first.short_name, "johndoe")

        user_last = User(username="janedoe", last_name="Doe")
        self.assertEqual(user_last.full_name, "janedoe")
        self.assertEqual(user_last.short_name, "janedoe")

    def test_user_short_name_formatting(self):
        """Test short_name returns initial + last_name correctly."""
        user = User(username="johndoe", first_name="john", last_name="Doe")
        self.assertEqual(user.short_name, "J. Doe")

    def test_set_pin_and_check_pin(self):
        """Test setting and verifying PIN hashes without DB writes."""
        user = User(username="pinuser")
        user.set_pin("1234")
        self.assertIsNotNone(user.pin)
        self.assertNotEqual(user.pin, "1234")
        self.assertTrue(user.check_pin("1234"))
        self.assertFalse(user.check_pin("9999"))

    def test_set_pin_none_clears_pin(self):
        """Test setting PIN to None/empty clears the field."""
        user = User(username="pinuser")
        user.set_pin("")
        self.assertIsNone(user.pin)

    def test_check_pin_returns_false_when_none(self):
        """Test check_pin returns False if pin or input is None/empty."""
        user = User(username="nopinuser")
        self.assertFalse(user.check_pin("1234"))
        self.assertFalse(user.check_pin(""))

    @patch("apps.users.models.check_password")
    def test_check_pin_handles_exception(self, mock_check_password):
        """Test check_pin safely catches exceptions."""
        mock_check_password.side_effect = Exception("Crypto error")
        user = User(username="pinuser")
        user.set_pin("1234")
        self.assertFalse(user.check_pin("1234"))

    def test_driver_commission_str(self):
        """Test DriverCommission string representation."""
        user = User(username="driver1")
        product = Product(name="Gallon Water", variation="Round")
        commission = DriverCommission(driver=user, product=product, rate_per_unit=5.00)
        self.assertEqual(str(commission), "driver1 - Gallon Water")

    def test_role_str(self):
        """Test Role __str__ representation."""
        role = Role(name="Admin")
        self.assertEqual(str(role), "Admin")

    def test_permission_str(self):
        """Test Permission __str__ representation."""
        role = Role(name="Admin")
        perm = Permission(role=role, action="dashboard")
        self.assertEqual(str(perm), "Admin - dashboard")

    def test_fake_user_repository_integration(self):
        """Test repository pattern with FakeUserRepository without spinning up DB."""
        repo = FakeUserRepository()
        user_data = repo.create_user(username="fakeuser", email="fake@example.com")
        
        self.assertEqual(user_data['username'], "fakeuser")
        retrieved = repo.get_by_username("fakeuser")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved['email'], "fake@example.com")

        self.assertIsNone(repo.get_by_username("nonexistent"))
        
        # Test update and delete in repo
        updated = repo.update(user_data['id'], email="updated@example.com")
        self.assertEqual(updated['email'], "updated@example.com")
        self.assertIsNone(repo.update("invalid_id", email="test"))

        deleted = repo.delete(user_data['id'])
        self.assertTrue(deleted)
        self.assertFalse(repo.delete("invalid_id"))

    def test_fake_role_and_permission_repositories(self):
        """Test role and permission management using fake repositories."""
        role_repo = FakeRoleRepository()
        perm_repo = FakePermissionRepository()

        admin_role = role_repo.create_role(name="Admin", description="Administrator")
        perm = perm_repo.create_permission(role_id=admin_role['id'], action="dashboard", can_read=True)

        self.assertEqual(admin_role['name'], "Admin")
        self.assertTrue(perm['can_read'])
        self.assertFalse(perm['can_write'])
