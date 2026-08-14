"""Tests for ``ScreenLockMiddleware`` — server-side enforcement of the
screen-lock session flag.

The idle lock-screen overlay is client-side Alpine.js state that
vanishes on refresh.  ``ScreenLockMiddleware`` closes that bypass by
redirecting any request (except the lock/verify/logout endpoints) to
the full-page lock screen when ``request.session['screen_locked']`` is
set.
"""
import json

from django.test import TestCase
from django.urls import reverse

from apps.users.models import Role, User


class ScreenLockMiddlewareTests(TestCase):
    def setUp(self):
        admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.user = User.objects.create_user(
            username="staff1",
            password="securepassword123",
            is_staff=True,
        )
        self.user.role = admin_role
        self.user.set_pin("1234")
        self.user.save()
        self.client.force_login(self.user)

    def _arm(self):
        """Set the server-side lock flag via the arm endpoint."""
        self.client.post(
            reverse("users:screen_lock_arm"),
            "{}",
            content_type="application/json",
        )

    # ------------------------------------------------------------------
    # Not locked — everything reachable
    # ------------------------------------------------------------------
    def test_unlocked_session_allows_dashboard(self):
        """Without the flag, the dashboard is reachable normally."""
        resp = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_user_never_locked(self):
        """Anonymous users are not subject to the lock (no session flag)."""
        client = self.client_class()
        # Even if somehow the flag were set, anonymous users are skipped.
        resp = client.get(reverse("users:index"))
        # Login page is reachable (302 redirect to login for index, or 200).
        self.assertIn(resp.status_code, (200, 302))

    # ------------------------------------------------------------------
    # Locked — protected pages redirect
    # ------------------------------------------------------------------
    def test_locked_redirects_dashboard_to_lock_page(self):
        """A locked session redirects a GET to the dashboard to the lock page."""
        self._arm()
        resp = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("users:screen_lock"))

    def test_locked_htmx_request_returns_hx_redirect(self):
        """HTMX requests get an HX-Redirect header instead of a 302."""
        self._arm()
        resp = self.client.get(
            reverse("analytics:dashboard"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["HX-Redirect"], reverse("users:screen_lock"))

    def test_locked_htmx_partial_redirects(self):
        """An HTMX partial endpoint is also caught by the middleware."""
        self._arm()
        resp = self.client.get(
            reverse("analytics:dashboard_stats"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["HX-Redirect"], reverse("users:screen_lock"))

    # ------------------------------------------------------------------
    # Locked — lock endpoints stay reachable
    # ------------------------------------------------------------------
    def test_locked_lock_page_reachable(self):
        """The lock page itself is reachable while locked."""
        self._arm()
        resp = self.client.get(reverse("users:screen_lock"))
        self.assertEqual(resp.status_code, 200)

    def test_locked_verify_endpoint_reachable(self):
        """The JSON verify endpoint is reachable while locked."""
        self._arm()
        resp = self.client.post(
            reverse("users:screen_lock_verify"),
            json.dumps({"pin": "1234"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["verified"])

    def test_locked_submit_endpoint_reachable(self):
        """The HTMX submit endpoint is reachable while locked."""
        self._arm()
        resp = self.client.post(
            reverse("users:screen_lock_submit"),
            {"pin": "1234"},
        )
        # Successful unlock returns an HX-Redirect to the dashboard.
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["HX-Redirect"], reverse("analytics:dashboard"))

    def test_locked_logout_reachable(self):
        """Logout is reachable while locked (escape hatch)."""
        self._arm()
        resp = self.client.post(reverse("users:logout"))
        self.assertEqual(resp.status_code, 302)

    # ------------------------------------------------------------------
    # Unlock restores access
    # ------------------------------------------------------------------
    def test_unlock_via_verify_restores_dashboard(self):
        """After a successful PIN verify, the dashboard is reachable again."""
        self._arm()
        self.client.post(
            reverse("users:screen_lock_verify"),
            json.dumps({"pin": "1234"}),
            content_type="application/json",
        )
        resp = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_unlock_via_submit_restores_dashboard(self):
        """After a successful PIN submit (HTMX), the dashboard is reachable."""
        self._arm()
        self.client.post(reverse("users:screen_lock_submit"), {"pin": "1234"})
        resp = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(resp.status_code, 200)

    # ------------------------------------------------------------------
    # Manual lock (screen_lock_view) also enforced
    # ------------------------------------------------------------------
    def test_manual_lock_then_dashboard_redirects(self):
        """Visiting /users/lock/ sets the flag; dashboard is then blocked."""
        self.client.get(reverse("users:screen_lock"))
        resp = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("users:screen_lock"))
