"""Tests for the soft-delete user flow (edit form → challenge → delete)."""
from django.test import TestCase

from apps.users.models import Role, User
from apps.users.services import generate_delete_challenge, soft_delete_user


class DeleteUserServiceTests(TestCase):
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

    def test_generate_delete_challenge_is_8_chars(self):
        """Challenge is exactly 8 alphanumeric characters."""
        challenge = generate_delete_challenge()
        self.assertEqual(len(challenge), 8)
        self.assertTrue(challenge.isalnum())

    def test_generate_delete_challenge_is_random(self):
        """Two consecutive challenges are (almost certainly) different."""
        challenges = {generate_delete_challenge() for _ in range(20)}
        self.assertGreater(len(challenges), 1)

    def test_soft_delete_sets_deleted_at_and_is_active_false(self):
        """Soft-delete stamps deleted_at and deactivates the account."""
        soft_delete_user(user=self.target, performed_by=self.admin)
        self.target.refresh_from_db()
        self.assertIsNotNone(self.target.deleted_at)
        self.assertFalse(self.target.is_active)

    def test_soft_delete_already_deleted_raises(self):
        """Cannot soft-delete a user that is already deleted."""
        soft_delete_user(user=self.target, performed_by=self.admin)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            soft_delete_user(user=self.target, performed_by=self.admin)

    def test_soft_delete_self_raises(self):
        """An admin cannot delete their own account."""
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            soft_delete_user(user=self.admin, performed_by=self.admin)


class DeleteUserViewTests(TestCase):
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
        return self.client.session.get(f"delete_challenge:{self.target.pk}", "")

    def test_edit_form_includes_delete_button_and_challenge(self):
        """The edit form renders the delete button and an 8-char challenge."""
        response = self._load_edit_form()
        self.assertContains(response, "Delete User")
        self.assertContains(response, "Confirmation code")
        # The challenge is stored in the session.
        self.assertEqual(len(self._session_challenge()), 8)

    def test_edit_form_hides_delete_for_self(self):
        """The delete button is hidden when editing your own account."""
        response = self.client.get(
            f"/user/{self.admin.pk}/edit/",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Delete User")

    def test_delete_with_correct_challenge_succeeds(self):
        """Posting the correct challenge and PIN soft-deletes the user."""
        self._load_edit_form()
        challenge = self._session_challenge()
        response = self.client.post(
            f"/user/{self.target.pk}/delete/",
            {"delete_challenge": challenge, "pin": "1234"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Deleted")
        self.target.refresh_from_db()
        self.assertIsNotNone(self.target.deleted_at)
        self.assertFalse(self.target.is_active)
        # The spent challenge is cleared from the session.
        self.assertNotIn(
            f"delete_challenge:{self.target.pk}", self.client.session
        )
        # The directory table refresh is triggered.
        self.assertIn("refreshUsersTable", response.headers.get("HX-Trigger", ""))

    def test_delete_with_wrong_challenge_fails(self):
        """A wrong challenge code does not delete the user."""
        self._load_edit_form()
        response = self.client.post(
            f"/user/{self.target.pk}/delete/",
            {"delete_challenge": "WRONGCODE"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not match")
        self.target.refresh_from_db()
        self.assertIsNone(self.target.deleted_at)
        self.assertTrue(self.target.is_active)

    def test_delete_without_session_challenge_regenerates(self):
        """A POST with no prior session challenge re-renders the form with an error."""
        response = self.client.post(
            f"/user/{self.target.pk}/delete/",
            {"delete_challenge": "ANYCODE"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "delete session expired")
        self.target.refresh_from_db()
        self.assertIsNone(self.target.deleted_at)

    def test_delete_requires_staff_permission(self):
        """A non-staff user cannot delete."""
        self.client.logout()
        regular = User.objects.create_user(
            username="regular",
            password="securepassword123",
        )
        self.client.force_login(regular)
        response = self.client.post(
            f"/user/{self.target.pk}/delete/",
            {"delete_challenge": "ANYCODE"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 403)

    def test_deleted_user_excluded_from_directory_lookup(self):
        """After deletion, get_user_by_id returns None for the user."""
        from apps.users.selectors import get_user_by_id
        self._load_edit_form()
        challenge = self._session_challenge()
        self.client.post(
            f"/user/{self.target.pk}/delete/",
            {"delete_challenge": challenge, "pin": "1234"},
            HTTP_HX_REQUEST="true",
        )
        self.assertIsNone(get_user_by_id(self.admin, self.target.pk))
