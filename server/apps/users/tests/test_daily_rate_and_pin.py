"""Tests for the Staff daily rate field and PIN-gated user mutations."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.users.models import Role, User
from apps.users.services import create_user_account, validate_user_pin


class DailyRateModelTests(TestCase):
    def setUp(self):
        self.staff_role, _ = Role.objects.get_or_create(name="Staff")
        self.driver_role, _ = Role.objects.get_or_create(name="Driver")
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.admin = User.objects.create_user(
            username="admin", password="securepassword123", is_staff=True,
        )
        self.admin.role = self.admin_role
        self.admin.save()

    def test_user_has_daily_rate_field_with_default_zero(self):
        """New users default to a zero daily rate."""
        user = User.objects.create_user(username="newuser", password="pass12345")
        self.assertEqual(user.daily_rate, Decimal("0.00"))

    def test_daily_rate_can_be_set_and_retrieved(self):
        """daily_rate stores and returns a Decimal value."""
        user = User.objects.create_user(username="staff1", password="pass12345")
        user.daily_rate = Decimal("550.00")
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.daily_rate, Decimal("550.00"))


class CreateUserServiceDailyRateTests(TestCase):
    def setUp(self):
        self.staff_role, _ = Role.objects.get_or_create(name="Staff")
        self.driver_role, _ = Role.objects.get_or_create(name="Driver")
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.admin = User.objects.create_user(
            username="admin", password="securepassword123", is_staff=True,
        )
        self.admin.role = self.admin_role
        self.admin.save()

    def test_create_staff_with_daily_rate(self):
        """create_user_account stores the daily_rate for Staff users."""
        user = create_user_account(
            username="staffpay",
            first_name="Staff",
            last_name="Member",
            email="",
            role=self.staff_role,
            company_id=None,
            performed_by=self.admin,
            daily_rate=Decimal("500.00"),
        )
        user.refresh_from_db()
        self.assertEqual(user.daily_rate, Decimal("500.00"))

    def test_create_staff_without_daily_rate_defaults_to_zero(self):
        """Staff without an explicit daily_rate gets 0.00."""
        user = create_user_account(
            username="staffnopay",
            first_name="",
            last_name="",
            email="",
            role=self.staff_role,
            company_id=None,
            performed_by=self.admin,
        )
        user.refresh_from_db()
        self.assertEqual(user.daily_rate, Decimal("0.00"))

    def test_create_driver_ignores_daily_rate(self):
        """daily_rate is not stored for Driver role users."""
        user = create_user_account(
            username="driver1",
            first_name="",
            last_name="",
            email="",
            role=self.driver_role,
            company_id=None,
            performed_by=self.admin,
            daily_rate=Decimal("999.00"),
        )
        user.refresh_from_db()
        self.assertEqual(user.daily_rate, Decimal("0.00"))

    def test_create_staff_with_negative_daily_rate_raises(self):
        """A negative daily rate is rejected."""
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            create_user_account(
                username="negpay",
                first_name="",
                last_name="",
                email="",
                role=self.staff_role,
                company_id=None,
                performed_by=self.admin,
                daily_rate=Decimal("-100.00"),
            )

    def test_create_staff_with_invalid_daily_rate_raises(self):
        """A non-numeric daily rate is rejected."""
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            create_user_account(
                username="badpay",
                first_name="",
                last_name="",
                email="",
                role=self.staff_role,
                company_id=None,
                performed_by=self.admin,
                daily_rate="not-a-number",
            )


class AddUserViewPinAndDailyRateTests(TestCase):
    def setUp(self):
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.staff_role, _ = Role.objects.get_or_create(name="Staff")
        self.driver_role, _ = Role.objects.get_or_create(name="Driver")
        self.admin = User.objects.create_user(
            username="admin", password="securepassword123", is_staff=True,
        )
        self.admin.role = self.admin_role
        self.admin.set_pin("1234")
        self.admin.save()
        self.client.force_login(self.admin)

    def test_add_user_form_renders_daily_rate_field(self):
        """The add user form includes the daily rate input."""
        response = self.client.get("/user/add/", HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "daily_rate")
        self.assertContains(response, "Daily Rate")

    def test_add_user_form_renders_pin_modal(self):
        """The add user form includes the PIN verification modal."""
        response = self.client.get("/user/add/", HTTP_HX_REQUEST="true")
        self.assertContains(response, "showPinModal")
        self.assertContains(response, "Confirm with PIN")

    def test_add_staff_with_pin_and_daily_rate_succeeds(self):
        """Creating a Staff user with correct PIN and daily rate works."""
        response = self.client.post(
            "/user/add/submit/",
            {
                "username": "newstaff",
                "first_name": "New",
                "last_name": "Staff",
                "email": "",
                "role": self.staff_role.id,
                "daily_rate": "450.00",
                "pin": "1234",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Temporary Password")
        user = User.objects.get(username="newstaff")
        self.assertEqual(user.daily_rate, Decimal("450.00"))

    def test_add_staff_without_pin_fails(self):
        """Creating a user without a PIN is rejected."""
        response = self.client.post(
            "/user/add/submit/",
            {
                "username": "nopinstaff",
                "first_name": "",
                "last_name": "",
                "email": "",
                "role": self.staff_role.id,
                "daily_rate": "500.00",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PIN is required")
        self.assertFalse(User.objects.filter(username="nopinstaff").exists())

    def test_add_user_with_wrong_pin_fails(self):
        """Creating a user with a wrong PIN is rejected."""
        response = self.client.post(
            "/user/add/submit/",
            {
                "username": "wrongpin",
                "first_name": "",
                "last_name": "",
                "email": "",
                "role": self.staff_role.id,
                "daily_rate": "500.00",
                "pin": "9999",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Incorrect PIN")
        self.assertFalse(User.objects.filter(username="wrongpin").exists())

    def test_add_staff_without_daily_rate_fails(self):
        """Creating a Staff user without a daily rate is rejected."""
        response = self.client.post(
            "/user/add/submit/",
            {
                "username": "noratestaff",
                "first_name": "",
                "last_name": "",
                "email": "",
                "role": self.staff_role.id,
                "pin": "1234",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Daily rate is required")
        self.assertFalse(User.objects.filter(username="noratestaff").exists())

    def test_add_driver_does_not_require_daily_rate(self):
        """Creating a Driver user does not require a daily rate."""
        response = self.client.post(
            "/user/add/submit/",
            {
                "username": "newdriver",
                "first_name": "",
                "last_name": "",
                "email": "",
                "role": self.driver_role.id,
                "pin": "1234",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Temporary Password")
        user = User.objects.get(username="newdriver")
        self.assertEqual(user.daily_rate, Decimal("0.00"))


class EditUserViewPinAndDailyRateTests(TestCase):
    def setUp(self):
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.staff_role, _ = Role.objects.get_or_create(name="Staff")
        self.driver_role, _ = Role.objects.get_or_create(name="Driver")
        self.admin = User.objects.create_user(
            username="admin", password="securepassword123", is_staff=True,
        )
        self.admin.role = self.admin_role
        self.admin.set_pin("1234")
        self.admin.save()
        self.target = User.objects.create_user(
            username="targetstaff", password="pass12345", is_staff=True,
        )
        self.target.role = self.staff_role
        self.target.daily_rate = Decimal("400.00")
        self.target.save()
        self.client.force_login(self.admin)

    def test_edit_form_renders_daily_rate_field(self):
        """The edit form includes the daily rate input."""
        response = self.client.get(
            f"/user/{self.target.pk}/edit/", HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "daily_rate")
        self.assertContains(response, "Daily Rate")
        self.assertContains(response, "400.00")

    def test_edit_form_renders_pin_modal(self):
        """The edit form includes the PIN verification modal."""
        response = self.client.get(
            f"/user/{self.target.pk}/edit/", HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "showPinModal")
        self.assertContains(response, "Confirm with PIN")

    def test_edit_user_with_correct_pin_saves_daily_rate(self):
        """Editing a user with correct PIN saves the new daily rate."""
        response = self.client.post(
            f"/user/{self.target.pk}/edit/submit/",
            {
                "username": "targetstaff",
                "first_name": "Target",
                "last_name": "Staff",
                "email": "",
                "role": self.staff_role.id,
                "daily_rate": "600.00",
                "is_active": "on",
                "pin": "1234",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.daily_rate, Decimal("600.00"))

    def test_edit_user_without_pin_fails(self):
        """Editing a user without a PIN is rejected."""
        response = self.client.post(
            f"/user/{self.target.pk}/edit/submit/",
            {
                "username": "targetstaff",
                "first_name": "Target",
                "last_name": "Staff",
                "email": "",
                "role": self.staff_role.id,
                "daily_rate": "600.00",
                "is_active": "on",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PIN is required")
        self.target.refresh_from_db()
        self.assertEqual(self.target.daily_rate, Decimal("400.00"))

    def test_edit_user_with_wrong_pin_fails(self):
        """Editing a user with a wrong PIN is rejected."""
        response = self.client.post(
            f"/user/{self.target.pk}/edit/submit/",
            {
                "username": "targetstaff",
                "first_name": "Target",
                "last_name": "Staff",
                "email": "",
                "role": self.staff_role.id,
                "daily_rate": "600.00",
                "is_active": "on",
                "pin": "0000",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Incorrect PIN")
        self.target.refresh_from_db()
        self.assertEqual(self.target.daily_rate, Decimal("400.00"))

    def test_edit_staff_without_daily_rate_fails(self):
        """Editing a Staff user without a daily rate is rejected."""
        response = self.client.post(
            f"/user/{self.target.pk}/edit/submit/",
            {
                "username": "targetstaff",
                "first_name": "Target",
                "last_name": "Staff",
                "email": "",
                "role": self.staff_role.id,
                "is_active": "on",
                "pin": "1234",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Daily rate is required")
        self.target.refresh_from_db()
        self.assertEqual(self.target.daily_rate, Decimal("400.00"))


class DeactivateUserPinTests(TestCase):
    def setUp(self):
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.admin = User.objects.create_user(
            username="testadmin", password="securepassword123", is_staff=True,
        )
        self.admin.role = self.admin_role
        self.admin.set_pin("1234")
        self.admin.save()
        self.target = User.objects.create_user(
            username="targetuser", password="pass12345", is_staff=True,
        )
        self.client.force_login(self.admin)

    def _load_edit_form(self):
        response = self.client.get(
            f"/user/{self.target.pk}/edit/", HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        return response

    def _session_challenge(self) -> str:
        return self.client.session.get(f"deactivate_challenge:{self.target.pk}", "")

    def test_deactivate_with_correct_challenge_and_pin_succeeds(self):
        """Deactivation succeeds with both the correct challenge code and PIN."""
        self._load_edit_form()
        challenge = self._session_challenge()
        response = self.client.post(
            f"/user/{self.target.pk}/deactivate/",
            {"deactivate_challenge": challenge, "pin": "1234"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Deactivated")
        self.target.refresh_from_db()
        self.assertIsNotNone(self.target.deactivated_at)

    def test_deactivate_with_correct_challenge_but_wrong_pin_fails(self):
        """Deactivation fails when the PIN is wrong even if the challenge is correct."""
        self._load_edit_form()
        challenge = self._session_challenge()
        response = self.client.post(
            f"/user/{self.target.pk}/deactivate/",
            {"deactivate_challenge": challenge, "pin": "9999"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Incorrect PIN")
        self.target.refresh_from_db()
        self.assertIsNone(self.target.deactivated_at)

    def test_deactivate_with_correct_challenge_but_no_pin_fails(self):
        """Deactivation fails when no PIN is provided even if the challenge is correct."""
        self._load_edit_form()
        challenge = self._session_challenge()
        response = self.client.post(
            f"/user/{self.target.pk}/deactivate/",
            {"deactivate_challenge": challenge},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PIN is required")
        self.target.refresh_from_db()
        self.assertIsNone(self.target.deactivated_at)


class GenerateTempPasswordPinTests(TestCase):
    def setUp(self):
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.admin = User.objects.create_user(
            username="admin", password="securepassword123", is_staff=True,
        )
        self.admin.role = self.admin_role
        self.admin.set_pin("1234")
        self.admin.save()
        self.target = User.objects.create_user(
            username="targetuser", password="pass12345", is_staff=True,
        )
        self.client.force_login(self.admin)

    def test_generate_temp_password_with_correct_pin_succeeds(self):
        """Temp password generation succeeds with the correct PIN."""
        response = self.client.post(
            f"/user/{self.target.pk}/temp-password/",
            {"pin": "1234"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Temporary Password")

    def test_generate_temp_password_with_wrong_pin_fails(self):
        """Temp password generation fails with a wrong PIN."""
        response = self.client.post(
            f"/user/{self.target.pk}/temp-password/",
            {"pin": "9999"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Incorrect PIN", status_code=403)

    def test_generate_temp_password_without_pin_fails(self):
        """Temp password generation fails without a PIN."""
        response = self.client.post(
            f"/user/{self.target.pk}/temp-password/",
            {},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "PIN is required", status_code=403)


class StaffDetailDailyRateDisplayTests(TestCase):
    def setUp(self):
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.staff_role, _ = Role.objects.get_or_create(name="Staff")
        self.admin = User.objects.create_user(
            username="admin", password="securepassword123", is_staff=True,
        )
        self.admin.role = self.admin_role
        self.admin.save()
        self.staff = User.objects.create_user(
            username="staff1", password="pass12345", is_staff=True,
        )
        self.staff.role = self.staff_role
        self.staff.daily_rate = Decimal("550.00")
        self.staff.save()
        self.client.force_login(self.admin)

    def test_staff_detail_shows_daily_rate_stat_card(self):
        """The staff user detail view shows the daily rate as a stat card."""
        from apps.employees.selectors import get_user_detail_context
        context = get_user_detail_context(self.admin, self.staff.id)
        self.assertIsNotNone(context)
        self.assertTrue(context.get("is_staff"))
        staff_stats = context.get("staff_stats", [])
        self.assertTrue(any(s["key"] == "daily_rate" for s in staff_stats))
        daily_rate_stat = next(s for s in staff_stats if s["key"] == "daily_rate")
        self.assertEqual(daily_rate_stat["value"], "₱550.00")


class ValidateUserPinTests(TestCase):
    """Unit tests for the centralized validate_user_pin service."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="pinuser",
            password="securepassword123",
        )
        self.user.set_pin("1234")
        self.user.save()

    def test_valid_pin_passes(self):
        # Should not raise any exception
        validate_user_pin(user=self.user, pin="1234")

    def test_valid_pin_with_whitespace_passes(self):
        # Whitespace should be stripped cleanly
        validate_user_pin(user=self.user, pin="  1234  ")

    def test_wrong_pin_raises_validation_error(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_user_pin(user=self.user, pin="9999")
        self.assertEqual(ctx.exception.message, "Incorrect PIN.")

    def test_empty_pin_raises_default_message(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_user_pin(user=self.user, pin="")
        self.assertEqual(ctx.exception.message, "PIN is required.")

    def test_none_pin_raises_default_message(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_user_pin(user=self.user, pin=None)
        self.assertEqual(ctx.exception.message, "PIN is required.")

    def test_empty_pin_raises_custom_message(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_user_pin(
                user=self.user,
                pin="   ",
                required_message="Custom PIN required message.",
            )
        self.assertEqual(ctx.exception.message, "Custom PIN required message.")

    def test_user_without_pin_configured_raises_descriptive_error(self):
        self.user.pin = None
        self.user.save()
        with self.assertRaises(ValidationError) as ctx:
            validate_user_pin(user=self.user, pin="1234")
        self.assertIn("No PIN is configured for your account", str(ctx.exception.message))
