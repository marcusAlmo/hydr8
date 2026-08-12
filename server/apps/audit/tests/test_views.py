"""Tests for the audit log views."""
from django.test import TestCase

from apps.users.models import User


class AuditLogViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.client.login(username="testuser", password="testpass123")

    def test_audit_log_page_renders(self):
        """The audit log page renders with 200 status for authenticated users."""
        response = self.client.get("/audit/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Audit Log")

    def test_audit_log_page_requires_login(self):
        """Unauthenticated users are redirected to login."""
        self.client.logout()
        response = self.client.get("/audit/")
        self.assertEqual(response.status_code, 302)

    def test_detail_view_returns_404_for_nonexistent_entry(self):
        response = self.client.get("/audit/99999/")
        self.assertEqual(response.status_code, 404)
