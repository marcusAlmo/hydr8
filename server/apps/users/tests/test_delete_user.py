"""Tests for the user activation/deactivation flow (edit form → challenge → status)."""
from django.test import TestCase

from apps.users.models import Role, User
from apps.users.services import (
    activate_user,
    deactivate_user,
    generate_deactivate_challenge,
)


class DeactivateUserServiceTests(TestCase):
    def setUp(self):
        admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.admin = User.objects.create_user(
            username="admin",
            password="securepassword123",
            is_staff=True,
        )
        self.admin.role = admin_role
        self.admin.save()
        self.target = User.objects.create_user(
            username="targetuser",
            password="securepassword123",
            is_staff=True,
        )

    def test_generate_deactivate_challenge_is_8_chars(self):
        """Challenge is exactly 8 alphanumeric characters."""
        challenge = generate_deactivate_challenge()
        self.assertEqual(len(challenge), 8)
        self.assertTrue(challenge.isalnum())

    def test_generate_deactivate_challenge_is_random(self):
        """Two consecutive challenges are (almost certainly) different."""
        challenges = {generate_deactivate_challenge() for _ in range(20)}
        self.assertGreater(len(challenges), 1)

    def test_deactivate_sets_deactivated_at_and_is_active_false(self):
        """Deactivation stamps deactivated_at and marks the account inactive."""
        deactivate_user(user=self.target, performed_by=self.admin)
        self.target.refresh_from_db()
        self.assertIsNotNone(self.target.deactivated_at)
        self.assertFalse(self.target.is_active)

    def test_deactivate_already_deactivated_raises(self):
        """Cannot deactivate a user that is already deactivated."""
        deactivate_user(user=self.target, performed_by=self.admin)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            deactivate_user(user=self.target, performed_by=self.admin)

    def test_deactivate_self_raises(self):
        """An admin cannot deactivate their own account."""
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            deactivate_user(user=self.admin, performed_by=self.admin)

    def test_activate_clears_deactivated_at_and_is_active_true(self):
        """Activation clears deactivated_at and marks the account active."""
        deactivate_user(user=self.target, performed_by=self.admin)
        activate_user(user=self.target, performed_by=self.admin)
        self.target.refresh_from_db()
        self.assertIsNone(self.target.deactivated_at)
        self.assertTrue(self.target.is_active)


class DeactivateUserViewTests(TestCase):
    def setUp(self):
        admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.admin = User.objects.create_user(
            username="admin",
            password="securepassword123",
            is_staff=True,
        )
        self.admin.role = admin_role
        self.admin.set_pin("1234")
        self.admin.save()
        self.target = User.objects.create_user(
            username="targetuser",
            password="securepassword123",
            is_staff=True,
        )
        self.client.force_login(self.admin)

    def _load_edit_form(self):
        """GET the edit form to seed the session challenge."""
        response = self.client.get(
            f"/user/{self.target.pk}/edit/",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        return response

    def _session_challenge(self) -> str:
        return self.client.session.get(f"deactivate_challenge:{self.target.pk}", "")

    def test_edit_form_includes_deactivate_button_and_challenge(self):
        """The edit form renders the deactivate button and an 8-char challenge."""
        response = self._load_edit_form()
        self.assertContains(response, "Deactivate User")
        self.assertContains(response, "Confirmation code")
        # The challenge is stored in the session.
        self.assertEqual(len(self._session_challenge()), 8)

    def test_edit_form_hides_deactivate_for_self(self):
        """The deactivate button is hidden when editing your own account."""
        response = self.client.get(
            f"/user/{self.admin.pk}/edit/",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Deactivate User")

    def test_deactivate_with_correct_challenge_succeeds(self):
        """Posting the correct challenge and PIN deactivates the user."""
        self._load_edit_form()
        challenge = self._session_challenge()
        response = self.client.post(
            f"/user/{self.target.pk}/deactivate/",
            {"deactivate_challenge": challenge, "status_pin": "1234"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Deactivated")
        self.target.refresh_from_db()
        self.assertIsNotNone(self.target.deactivated_at)
        self.assertFalse(self.target.is_active)
        # The spent challenge is cleared from the session.
        self.assertNotIn(
            f"deactivate_challenge:{self.target.pk}", self.client.session
        )
        # The directory table refresh is triggered.
        self.assertIn("refreshUsersTable", response.headers.get("HX-Trigger", ""))

    def test_deactivate_with_wrong_challenge_fails(self):
        """A wrong challenge code does not deactivate the user."""
        self._load_edit_form()
        response = self.client.post(
            f"/user/{self.target.pk}/deactivate/",
            {"deactivate_challenge": "WRONGCODE"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not match")
        self.target.refresh_from_db()
        self.assertIsNone(self.target.deactivated_at)
        self.assertTrue(self.target.is_active)

    def test_deactivate_without_session_challenge_regenerates(self):
        """A POST with no prior session challenge re-renders the form with an error."""
        response = self.client.post(
            f"/user/{self.target.pk}/deactivate/",
            {"deactivate_challenge": "ANYCODE"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "session expired")
        self.target.refresh_from_db()
        self.assertIsNone(self.target.deactivated_at)

    def test_deactivate_requires_admin_permission(self):
        """A non-admin user cannot deactivate."""
        self.client.logout()
        regular = User.objects.create_user(
            username="regular",
            password="securepassword123",
        )
        self.client.force_login(regular)
        response = self.client.post(
            f"/user/{self.target.pk}/deactivate/",
            {"deactivate_challenge": "ANYCODE"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 403)

    def test_deactivated_user_still_findable_by_id(self):
        """After deactivation get_user_by_id still returns the user (not deleted)."""
        from apps.users.selectors import get_user_by_id
        self._load_edit_form()
        challenge = self._session_challenge()
        self.client.post(
            f"/user/{self.target.pk}/deactivate/",
            {"deactivate_challenge": challenge, "status_pin": "1234"},
            HTTP_HX_REQUEST="true",
        )
        # The user is not deleted, only deactivated, so the selector still finds it.
        self.assertIsNotNone(get_user_by_id(self.admin, self.target.pk))


class ActivateUserViewTests(TestCase):
    def setUp(self):
        admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.admin = User.objects.create_user(
            username="admin",
            password="securepassword123",
            is_staff=True,
        )
        self.admin.role = admin_role
        self.admin.set_pin("1234")
        self.admin.save()
        self.target = User.objects.create_user(
            username="targetuser",
            password="securepassword123",
            is_staff=True,
        )
        self.target.deactivated_at = "2026-01-01T00:00:00Z"
        self.target.is_active = False
        self.target.save()
        self.client.force_login(self.admin)

    def test_activate_with_pin_succeeds(self):
        """Posting the correct PIN reactivates a deactivated user."""
        response = self.client.post(
            f"/user/{self.target.pk}/activate/",
            {"status_pin": "1234"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Activated")
        self.target.refresh_from_db()
        self.assertIsNone(self.target.deactivated_at)
        self.assertTrue(self.target.is_active)

    def test_activate_with_wrong_pin_fails(self):
        """A wrong PIN does not activate the user."""
        response = self.client.post(
            f"/user/{self.target.pk}/activate/",
            {"status_pin": "9999"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Incorrect PIN")
        self.target.refresh_from_db()
        self.assertIsNotNone(self.target.deactivated_at)
        self.assertFalse(self.target.is_active)
