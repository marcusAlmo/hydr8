"""Tests for the idle lock-screen overlay JSON endpoint.

Covers ``screen_lock_verify_view`` — the JSON PIN-verification endpoint
used by the Alpine.js overlay in ``base.html``.  Verifies:

* Correct PIN unlocks and clears the session attempt counter.
* Wrong PIN increments the counter and reports attempts remaining.
* After 3 failures the user is logged out and a redirect URL is
  returned.
* Anonymous users are redirected to login (``@login_required``).
* Non-POST methods are rejected (``@require_http_methods``).
* Malformed JSON / missing PIN returns a 400.
"""
import json

from django.test import TestCase
from django.urls import reverse

from apps.users.models import User


class ScreenLockVerifyViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="staff1",
            password="securepassword123",
            is_staff=True,
        )
        self.user.set_pin("1234")
        self.user.save()
        self.client.force_login(self.user)
        self.url = reverse("users:screen_lock_verify")

    def _post(self, payload: dict | str):
        """POST a JSON body (or raw string) to the verify endpoint."""
        if isinstance(payload, str):
            data = payload
            content_type = "application/json"
        else:
            data = json.dumps(payload)
            content_type = "application/json"
        return self.client.post(self.url, data, content_type=content_type)

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------
    def test_correct_pin_unlocks(self):
        """A correct PIN returns verified=true and clears attempts."""
        # Seed a failed attempt first to prove it gets cleared.
        self._post({"pin": "0000"})
        self.assertEqual(self.client.session.get("pin_attempts"), 1)

        resp = self._post({"pin": "1234"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["verified"])
        self.assertNotIn("pin_attempts", self.client.session)
        self.assertNotIn("screen_locked", self.client.session)

    def test_correct_pin_with_no_prior_attempts(self):
        """First-try correct PIN works without any prior failures."""
        resp = self._post({"pin": "1234"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["verified"])

    # ------------------------------------------------------------------
    # Wrong PIN
    # ------------------------------------------------------------------
    def test_wrong_pin_increments_attempts(self):
        """A wrong PIN returns verified=false and attempts_left."""
        resp = self._post({"pin": "9999"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["verified"])
        self.assertEqual(body["attempts_left"], 2)
        self.assertEqual(self.client.session.get("pin_attempts"), 1)

    def test_wrong_pin_second_attempt(self):
        """Second wrong PIN shows 1 attempt left."""
        self._post({"pin": "0000"})
        resp = self._post({"pin": "0000"})
        body = resp.json()
        self.assertFalse(body["verified"])
        self.assertEqual(body["attempts_left"], 1)
        self.assertEqual(self.client.session.get("pin_attempts"), 2)

    # ------------------------------------------------------------------
    # 3-attempt lockout → logout
    # ------------------------------------------------------------------
    def test_three_failures_log_out_and_redirect(self):
        """After 3 wrong PINs the user is logged out and redirect returned."""
        self._post({"pin": "0000"})
        self._post({"pin": "0000"})
        resp = self._post({"pin": "0000"})

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["verified"])
        self.assertTrue(body["logged_out"])
        self.assertIn("redirect", body)
        self.assertEqual(body["redirect"], reverse("users:index"))

        # Session is destroyed — user is no longer authenticated.
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_success_after_two_failures_resets_counter(self):
        """A correct PIN after 2 failures clears the attempt counter."""
        self._post({"pin": "0000"})
        self._post({"pin": "0000"})
        self.assertEqual(self.client.session.get("pin_attempts"), 2)

        resp = self._post({"pin": "1234"})
        self.assertTrue(resp.json()["verified"])
        self.assertNotIn("pin_attempts", self.client.session)

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------
    def test_missing_pin_returns_400(self):
        """An empty PIN field returns a 400 with an error message."""
        resp = self._post({"pin": ""})
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertFalse(body["verified"])
        self.assertIn("error", body)

    def test_no_pin_key_returns_400(self):
        """Missing pin key in JSON body returns 400."""
        resp = self._post({})
        self.assertEqual(resp.status_code, 400)

    def test_malformed_json_returns_400(self):
        """Malformed JSON body returns 400."""
        resp = self._post("{not json")
        self.assertEqual(resp.status_code, 400)

    def test_empty_body_returns_400(self):
        """An empty POST body returns 400 (not 500)."""
        resp = self.client.post(self.url, "", content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    # ------------------------------------------------------------------
    # Auth & method guards
    # ------------------------------------------------------------------
    def test_anonymous_user_redirected(self):
        """Unauthenticated requests hit @login_required → redirect."""
        client = self.client_class()
        resp = client.post(
            self.url,
            json.dumps({"pin": "1234"}),
            content_type="application/json",
        )
        # @login_required issues a 302 redirect to /users/login/.
        self.assertEqual(resp.status_code, 302)

    def test_get_method_not_allowed(self):
        """GET is rejected by @require_http_methods."""
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)

    # ------------------------------------------------------------------
    # Context processor
    # ------------------------------------------------------------------
    def test_context_processor_exposes_timeout_for_authenticated_user(self):
        """The lockscreen_timeout context processor injects the value."""
        resp = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(resp.status_code, 200)
        # The context processor always injects the key; for the test
        # user (no company) it falls back to the default (5).
        self.assertIn("lockscreen_timeout_minutes", resp.context)
        self.assertGreater(resp.context["lockscreen_timeout_minutes"], 0)
