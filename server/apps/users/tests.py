from django.test import TestCase
from django.utils import timezone
from .models import User, Role, Permission

class UserModelTests(TestCase):
    def setUp(self):
        # Create a base role and permission
        self.role = Role.objects.create(name="Admin")
        self.permission = Permission.objects.create(
            role=self.role, 
            action="dashboard", 
            can_read=True, 
            can_write=False
        )
        
        # Create a test user
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="password123"
        )

    def test_user_initial_state(self):
        """Test that a user starts as active."""
        self.assertEqual(self.user.status, User.Status.ACTIVE)
        self.assertIsNone(self.user.deleted_at)
        self.assertTrue(self.user.is_account_active)

    def test_deactivate_user(self):
        """Test the encapsulate deactivate business logic."""
        self.user.deactivate()
        self.assertEqual(self.user.status, User.Status.DEACTIVATED)
        self.assertIsNotNone(self.user.deleted_at)
        self.assertFalse(self.user.is_account_active)

    def test_activate_user(self):
        """Test the encapsulate activate business logic."""
        self.user.deactivate() # Deactivate first
        self.user.activate()
        self.assertEqual(self.user.status, User.Status.ACTIVE)
        self.assertIsNone(self.user.deleted_at)
        self.assertTrue(self.user.is_account_active)

    def test_assign_role_success(self):
        """Test assigning an existing role."""
        success = self.user.assign_role("Admin")
        self.assertTrue(success)
        self.assertEqual(self.user.role, self.role)

    def test_assign_role_failure(self):
        """Test assigning a non-existent role."""
        success = self.user.assign_role("NonExistentRole")
        self.assertFalse(success)
        self.assertIsNone(self.user.role)

    def test_has_permission(self):
        """Test the has_permission RBAC logic."""
        self.user.assign_role("Admin")
        
        # Should have read access (as defined in setUp)
        self.assertTrue(self.user.has_permission("dashboard", "read"))
        
        # Should not have write access
        self.assertFalse(self.user.has_permission("dashboard", "write"))
        
        # Should handle non-existent actions gracefully
        self.assertFalse(self.user.has_permission("unknown_action", "read"))

    def test_custom_manager_active_users(self):
        """Test the SoftDeleteQuerySet for active users."""
        self.user.deactivate()
        
        active_users = User.objects.active_users()
        self.assertNotIn(self.user, active_users)
        
        self.user.activate()
        active_users_again = User.objects.active_users()
        self.assertIn(self.user, active_users_again)
