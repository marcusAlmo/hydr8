"""Tests for the audit log ACCESS event signal handlers."""
from django.test import TestCase

from auditlog.models import LogEntry
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
