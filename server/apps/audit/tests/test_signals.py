"""Tests for the audit log ACCESS event signal handlers."""
from auditlog.models import LogEntry
from django.test import TestCase

from apps.users.models import User


class LoginSignalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123",
            email="test@hydr8.io"
        )

    def test_login_creates_access_log_entry(self):
        self.client.login(username="testuser", password="testpass123")
        entries = LogEntry.objects.filter(
            action=LogEntry.Action.ACCESS,
            additional_data__event="login",
        )
        self.assertEqual(entries.count(), 1)
        entry = entries.first()
        self.assertEqual(entry.actor, self.user)
        self.assertEqual(entry.additional_data["event"], "login")

    def test_logout_creates_access_log_entry(self):
        self.client.login(username="testuser", password="testpass123")
        self.client.logout()
        entries = LogEntry.objects.filter(
            action=LogEntry.Action.ACCESS,
            additional_data__event="logout",
        )
        self.assertEqual(entries.count(), 1)

    def test_failed_login_creates_access_log_entry(self):
        response = self.client.post("/login/", {
            "username": "testuser",
            "password": "wrongpassword",
        }, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        entries = LogEntry.objects.filter(
            action=LogEntry.Action.ACCESS,
            additional_data__event="login_failed",
        )
        self.assertEqual(entries.count(), 1)
        entry = entries.first()
        self.assertIsNone(entry.actor)
        self.assertIn("testuser", entry.object_repr)

    def test_failed_login_log_entry_has_correlation_id(self):
        """The cid field must be populated from the project's correlation id
        contextvar (set by CorrelationIdMiddleware), not left as None."""
        response = self.client.post("/login/", {
            "username": "testuser",
            "password": "wrongpassword",
        }, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        entry = LogEntry.objects.filter(
            action=LogEntry.Action.ACCESS,
            additional_data__event="login_failed",
        ).order_by("-id").first()
        self.assertIsNotNone(entry.cid)
        # The cid must match the X-Correlation-ID header set by the middleware
        self.assertEqual(entry.cid, response.headers["X-Correlation-ID"])
