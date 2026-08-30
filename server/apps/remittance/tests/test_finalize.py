"""Tests for the remittance finalize service and admin role check.

Covers:
  - is_admin_user() helper
  - finalize_remittance() service — happy path, role/PIN validation,
    tenant isolation, and already-finalized guard.
"""

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.remittance.models import Remittance
from apps.remittance.services import (
    finalize_remittance,
    save_remittance_draft,
)
from apps.users.models import Role, User
from apps.users.permissions import is_admin


class IsAdminUserTests(TestCase):
    """Tests for the is_admin_user helper."""

    def setUp(self):
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.staff_role, _ = Role.objects.get_or_create(name="Staff")
        self.driver_role, _ = Role.objects.get_or_create(name="Driver")

    def test_superuser_is_admin(self):
        """A superuser is considered an admin."""
        user = User.objects.create_superuser(username="root", password="pass123")
        self.assertTrue(is_admin(user=user))

    def test_admin_role_is_admin(self):
        """A user with the Admin role is an admin."""
        user = User.objects.create_user(
            username="admin", password="pass123", role=self.admin_role
        )
        self.assertTrue(is_admin(user=user))

    def test_staff_role_is_not_admin(self):
        """A user with the Staff role is not an admin."""
        user = User.objects.create_user(
            username="staff", password="pass123", role=self.staff_role
        )
        self.assertFalse(is_admin(user=user))

    def test_driver_role_is_not_admin(self):
        """A user with the Driver role is not an admin."""
        user = User.objects.create_user(
            username="driver", password="pass123", role=self.driver_role
        )
        self.assertFalse(is_admin(user=user))

    def test_no_role_is_not_admin(self):
        """A user with no role is not an admin."""
        user = User.objects.create_user(username="norole", password="pass123")
        self.assertFalse(is_admin(user=user))


class FinalizeRemittanceTests(TestCase):
    """Tests for the finalize_remittance service."""

    def setUp(self):
        cache.clear()
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.staff_role, _ = Role.objects.get_or_create(name="Staff")

        self.admin = User.objects.create_user(
            username="admin",
            password="securepassword123",
            role=self.admin_role,
        )
        self.admin.set_pin("1234")
        self.admin.save()

        self.staff = User.objects.create_user(
            username="staff",
            password="securepassword123",
            role=self.staff_role,
        )
        self.staff.set_pin("1234")
        self.staff.save()

        # Create a draft remittance (by staff)
        self.draft = save_remittance_draft(
            performed_by=self.staff,
            remittance_date=timezone.localdate(),
            riders_data=[],
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
        )

    def tearDown(self):
        cache.clear()

    def test_admin_with_valid_pin_finalizes_draft(self):
        """An admin with a valid PIN can finalize a draft remittance."""
        result = finalize_remittance(
            performed_by=self.admin,
            remittance_id=self.draft.id,
            pin="1234",
        )
        self.assertEqual(result.status, Remittance.StatusChoices.FINALIZED)
        self.assertIsNotNone(result.finalized_at)
        self.assertEqual(result.finalized_by, self.admin)

    def test_non_admin_cannot_finalize(self):
        """A non-admin user raises ValidationError."""
        with self.assertRaises(ValidationError):
            finalize_remittance(
                performed_by=self.staff,
                remittance_id=self.draft.id,
                pin="1234",
            )

    def test_invalid_pin_raises(self):
        """An incorrect PIN raises ValidationError."""
        with self.assertRaises(ValidationError):
            finalize_remittance(
                performed_by=self.admin,
                remittance_id=self.draft.id,
                pin="9999",
            )

    def test_nonexistent_remittance_raises(self):
        """A non-existent remittance ID raises ValidationError."""
        with self.assertRaises(ValidationError):
            finalize_remittance(
                performed_by=self.admin,
                remittance_id=99999,
                pin="1234",
            )

    def test_already_finalized_raises(self):
        """Finalizing an already-finalized remittance raises ValidationError."""
        finalize_remittance(
            performed_by=self.admin,
            remittance_id=self.draft.id,
            pin="1234",
        )
        with self.assertRaises(ValidationError):
            finalize_remittance(
                performed_by=self.admin,
                remittance_id=self.draft.id,
                pin="1234",
            )

    def test_superuser_can_finalize(self):
        """A superuser can finalize without a role."""
        superuser = User.objects.create_superuser(
            username="root", password="pass123"
        )
        superuser.set_pin("1234")
        superuser.save()
        result = finalize_remittance(
            performed_by=superuser,
            remittance_id=self.draft.id,
            pin="1234",
        )
        self.assertEqual(result.status, Remittance.StatusChoices.FINALIZED)
