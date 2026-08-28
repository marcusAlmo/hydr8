"""Tests for the Remittance page and HTMX view endpoints."""
import json

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.users.models import Role, User


def _make_user(username, role_name, password="securepassword123"):
    """Create a test user with the named role and a usable password."""
    role, _ = Role.objects.get_or_create(name=role_name, company=None)
    user = User.objects.create_user(
        username=username,
        password=password,
        first_name="Test",
        last_name="User",
    )
    user.role = role
    user.save()
    return user


def _json_post(client, url, data):
    """POST a JSON body to a view."""
    return client.post(
        url,
        data=json.dumps(data),
        content_type="application/json",
    )


class AddRemittanceViewTests(TestCase):
    """Tests for the Add Remittance page (GET /remittance/add/)."""

    def setUp(self):
        cache.clear()
        self.admin = _make_user("admin_view", "Admin")
        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    def test_add_view_renders(self):
        """GET /remittance/add/ renders the add workflow for a logged-in user."""
        response = self.client.get(reverse("remittance:add"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "remittance/add_remittance.html")

    def test_add_view_accepts_date_query_param(self):
        """A valid `?date=` query is accepted without error."""
        response = self.client.get(reverse("remittance:add") + "?date=2026-08-01")
        self.assertEqual(response.status_code, 200)

    def test_add_view_ignores_invalid_date_param(self):
        """An invalid `?date=` query is ignored and the page still renders."""
        response = self.client.get(reverse("remittance:add") + "?date=not-a-date")
        self.assertEqual(response.status_code, 200)

    def test_add_view_requires_login(self):
        """Anonymous users are redirected to login."""
        self.client.logout()
        response = self.client.get(reverse("remittance:add"))
        self.assertEqual(response.status_code, 302)


class RemittanceHistoryViewTests(TestCase):
    """Tests for the admin-only Remittance History page."""

    def setUp(self):
        cache.clear()
        self.admin = _make_user("admin_hist", "Admin")
        self.staff = _make_user("staff_hist", "Staff")

    def tearDown(self):
        cache.clear()

    def test_history_renders_for_admin(self):
        """Admin users see the history page."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse("remittance:history"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "remittance/remittance_history.html")

    def test_history_forbidden_for_staff(self):
        """Staff users receive a 403."""
        self.client.force_login(self.staff)
        response = self.client.get(reverse("remittance:history"))
        self.assertEqual(response.status_code, 403)

    def test_history_forbidden_for_staff_htmx(self):
        """Staff HTMX requests still get a plain 403."""
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("remittance:history"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Forbidden", status_code=403)

    def test_history_requires_login(self):
        """Anonymous users are redirected."""
        response = self.client.get(reverse("remittance:history"))
        self.assertEqual(response.status_code, 302)


class CheckRemittanceDateViewTests(TestCase):
    """Tests for the check-date JSON endpoint."""

    def setUp(self):
        cache.clear()
        self.admin = _make_user("admin_check", "Admin")
        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    def test_missing_date_returns_400(self):
        """A request without a `date` parameter is rejected."""
        response = self.client.get(reverse("remittance:check_date"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["ok"], False)

    def test_invalid_date_returns_400(self):
        """A non-ISO `date` parameter is rejected."""
        response = self.client.get(
            reverse("remittance:check_date") + "?date=invalid"
        )
        self.assertEqual(response.status_code, 400)

    def test_valid_date_returns_ok(self):
        """A well-formed date returns an ok response."""
        response = self.client.get(
            reverse("remittance:check_date") + "?date=2026-08-28"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ok"], True)


class VerifyPinViewTests(TestCase):
    """Tests for the remittance PIN verification JSON endpoint."""

    def setUp(self):
        cache.clear()
        self.admin = _make_user("admin_pin", "Admin")
        self.admin.set_pin("1234")
        self.admin.save()
        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    def test_correct_pin_verifies(self):
        """The correct PIN returns verified: true."""
        response = _json_post(self.client, reverse("remittance:verify_pin"), {
            "pin": "1234",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["verified"])

    def test_missing_pin_returns_400(self):
        """An empty PIN is rejected."""
        response = _json_post(self.client, reverse("remittance:verify_pin"), {})
        self.assertEqual(response.status_code, 400)

    def test_wrong_pin_returns_attempts_left(self):
        """A wrong PIN decrements attempts but does not log out on the first try."""
        response = _json_post(self.client, reverse("remittance:verify_pin"), {
            "pin": "0000",
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["verified"])
        self.assertEqual(data["attempts_left"], 2)

    def test_three_wrong_pins_logout(self):
        """Three wrong PINs log the user out and signal a redirect."""
        for _ in range(2):
            _json_post(self.client, reverse("remittance:verify_pin"), {
                "pin": "0000",
            })

        response = _json_post(self.client, reverse("remittance:verify_pin"), {
            "pin": "0000",
        })
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["verified"])
        self.assertTrue(data["logged_out"])
        self.assertIn("redirect", data)


class CreateRemittanceViewTests(TestCase):
    """Tests for the create/finalize JSON endpoint."""

    def setUp(self):
        cache.clear()
        self.admin = _make_user("admin_create", "Admin")
        self.admin.set_pin("1234")
        self.admin.save()
        self.staff = _make_user("staff_create", "Staff")

    def tearDown(self):
        cache.clear()

    def _payload(self, **overrides):
        return {
            "mode": "draft",
            "riders": [],
            "expenses": [],
            "manualOffering": "0",
            "titheRate": "0.10",
            "otherSales": 0,
            "staff": [],
            **overrides,
        }

    def test_invalid_json_returns_400(self):
        """A non-JSON body returns a 400 error."""
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("remittance:create"),
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_staff_finalize_forbidden(self):
        """Staff cannot use finalize mode."""
        self.client.force_login(self.staff)
        response = _json_post(
            self.client,
            reverse("remittance:create"),
            self._payload(mode="finalize", pin="1234"),
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_finalize_wrong_pin_returns_400(self):
        """Admin with the wrong PIN gets a 400 before finalization."""
        self.client.force_login(self.admin)
        response = _json_post(
            self.client,
            reverse("remittance:create"),
            self._payload(mode="finalize", pin="0000"),
        )
        self.assertEqual(response.status_code, 400)

    def test_staff_can_save_draft(self):
        """Staff can save a draft remittance."""
        self.client.force_login(self.staff)
        response = _json_post(
            self.client,
            reverse("remittance:create"),
            self._payload(),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data.get("draft_saved"))

    def test_create_rejects_future_date(self):
        """A remittance date in the future is rejected."""
        self.client.force_login(self.staff)
        response = _json_post(
            self.client,
            reverse("remittance:create"),
            self._payload(remittanceDate="2099-01-01"),
        )
        self.assertEqual(response.status_code, 400)


class ClearDraftViewTests(TestCase):
    """Tests for the clear-draft JSON endpoint."""

    def setUp(self):
        cache.clear()
        self.admin = _make_user("admin_clear", "Admin")
        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    def test_invalid_json_returns_400(self):
        """A non-JSON body is rejected."""
        response = self.client.post(
            reverse("remittance:clear_draft"),
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_date_returns_400(self):
        """An invalid `remittanceDate` is rejected."""
        response = _json_post(
            self.client,
            reverse("remittance:clear_draft"),
            {"remittanceDate": "invalid"},
        )
        self.assertEqual(response.status_code, 400)

    def test_valid_request_returns_ok(self):
        """A well-formed request succeeds even when no draft exists."""
        response = _json_post(
            self.client,
            reverse("remittance:clear_draft"),
            {"remittanceDate": "2026-08-28"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertFalse(data["deleted"])
