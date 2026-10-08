"""Tests for multi-tenant user scoping and dual email/username authentication."""

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.settings.models import Company
from apps.users.backends import EmailOrUsernameBackend
from apps.users.models import Role, User
from apps.users.selectors import get_user_by_id
from apps.users.services import create_user_account


class MultiTenantUserTests(TestCase):
    """Tests for TenantUserManager.for_user and user scoping."""

    def setUp(self):
        cache.clear()
        self.company_a = Company.objects.create(name="Company A")
        self.company_b = Company.objects.create(name="Company B")

        self.role_admin_a = Role.objects.create(name="Admin", company=self.company_a)
        self.role_admin_b = Role.objects.create(name="Admin", company=self.company_b)

        # Users in Company A
        self.admin_a = User.objects.create_user(
            username="admin_a",
            email="admin@companya.ph",
            password="password123",
            company=self.company_a,
            role=self.role_admin_a,
            is_staff=True,
        )
        self.staff_a = User.objects.create_user(
            username="staff_a",
            email="staff@companya.ph",
            password="password123",
            company=self.company_a,
        )

        # User in Company B
        self.admin_b = User.objects.create_user(
            username="admin_b",
            email="admin@companyb.ph",
            password="password123",
            company=self.company_b,
            role=self.role_admin_b,
            is_staff=True,
        )

        # Platform Superuser (no company)
        self.superuser = User.objects.create_superuser(
            username="superadmin",
            email="super@hydr8.ph",
            password="password123",
        )

    def tearDown(self):
        cache.clear()

    def test_for_user_filters_by_company(self):
        """User.objects.for_user only returns users belonging to the requester's company."""
        users_a = User.objects.for_user(self.admin_a)
        self.assertEqual(users_a.count(), 2)
        self.assertIn(self.admin_a, users_a)
        self.assertIn(self.staff_a, users_a)
        self.assertNotIn(self.admin_b, users_a)

        users_b = User.objects.for_user(self.admin_b)
        self.assertEqual(users_b.count(), 1)
        self.assertIn(self.admin_b, users_b)
        self.assertNotIn(self.admin_a, users_b)

    def test_for_user_superuser_sees_all(self):
        """Platform superuser sees users across all tenants."""
        all_users = User.objects.for_user(self.superuser)
        self.assertEqual(all_users.count(), 4)

    def test_get_user_by_id_scoped_to_tenant(self):
        """A tenant cannot retrieve a user belonging to another company."""
        # admin_a can see staff_a
        found = get_user_by_id(self.admin_a, str(self.staff_a.id))
        self.assertIsNotNone(found)
        self.assertEqual(found.id, self.staff_a.id)

        # admin_a CANNOT see admin_b
        hidden = get_user_by_id(self.admin_a, str(self.admin_b.id))
        self.assertIsNone(hidden)


class DualAuthBackendTests(TestCase):
    """Tests for EmailOrUsernameBackend dual authentication."""

    def setUp(self):
        cache.clear()
        self.backend = EmailOrUsernameBackend()
        self.company = Company.objects.create(name="Test Station")
        role = Role.objects.create(name="Staff", company=self.company)
        self.user = User.objects.create_user(
            username="station_cashier",
            email="cashier@teststation.ph",
            password="SecretPassword456!",
            company=self.company,
            role=role,
        )

    def tearDown(self):
        cache.clear()

    def test_authenticate_by_username(self):
        """User can authenticate using their standard username."""
        authenticated = self.backend.authenticate(
            request=None,
            username="station_cashier",
            password="SecretPassword456!",
        )
        self.assertIsNotNone(authenticated)
        self.assertEqual(authenticated.id, self.user.id)

    def test_authenticate_by_email_case_insensitive(self):
        """User can authenticate using their email address regardless of casing."""
        authenticated = self.backend.authenticate(
            request=None,
            username="CASHIER@TESTSTATION.PH",
            password="SecretPassword456!",
        )
        self.assertIsNotNone(authenticated)
        self.assertEqual(authenticated.id, self.user.id)

    def test_authenticate_wrong_password_fails(self):
        """Authentication fails with incorrect password."""
        authenticated = self.backend.authenticate(
            request=None,
            username="station_cashier",
            password="WrongPassword!",
        )
        self.assertIsNone(authenticated)

    def test_authenticate_soft_deleted_user_fails(self):
        """Soft-deleted users are prevented from authenticating."""
        from django.utils import timezone
        self.user.deleted_at = timezone.now()
        self.user.save(update_fields=["deleted_at"])

        authenticated = self.backend.authenticate(
            request=None,
            username="station_cashier",
            password="SecretPassword456!",
        )
        self.assertIsNone(authenticated)

    def test_create_user_account_rejects_duplicate_email(self):
        """Creating an account with an already existing email is rejected."""
        with self.assertRaises(ValidationError) as ctx:
            create_user_account(
                username="new_username",
                first_name="Jane",
                last_name="Doe",
                email="cashier@teststation.ph",  # Duplicate of self.user.email
                role=self.user.role,
                company_id=self.company.id,
                performed_by=self.user,
            )
        self.assertIn("email already exists", str(ctx.exception))
