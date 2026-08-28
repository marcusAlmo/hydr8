"""Tests for the audit log views."""
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.test import TestCase

from apps.users.models import User


class AuditLogViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.user.is_superuser = True
        self.user.save()
        self.client.login(username="testuser", password="testpass123")

    def tearDown(self):
        cache.clear()

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

    def test_audit_log_table_partial_for_htmx(self):
        """HTMX requests receive the table partial with an empty log JSON seed."""
        response = self.client.get("/audit/", HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "audit/partials/audit_log_table.html")
        self.assertEqual(response.context["logs_json"], "[]")

    def test_audit_log_forbidden_for_staff(self):
        """Non-admin users cannot access the audit log."""
        self.client.logout()
        staff = User.objects.create_user(
            username="staffaudit", password="testpass123"
        )
        staff.is_superuser = False
        staff.save()
        self.client.login(username="staffaudit", password="testpass123")

        response = self.client.get("/audit/")
        self.assertEqual(response.status_code, 403)

    def test_detail_view_returns_404_for_nonexistent_entry(self):
        response = self.client.get("/audit/99999/")
        self.assertEqual(response.status_code, 404)

    def test_detail_view_renders_with_changes_and_serialized_data(self):
        """The detail modal enriches a LogEntry with changes and pretty-printed data."""
        from auditlog.models import LogEntry

        ct = ContentType.objects.get_for_model(User)
        entry = LogEntry.objects.create(
            content_type=ct,
            object_pk=str(self.user.pk),
            object_repr="Test User",
            action=1,
            changes={"name": ["Old", "New"]},
            serialized_data={"id": 1, "name": "New"},
            additional_data={"ip": "127.0.0.1"},
            actor=self.user,
        )

        response = self.client.get(f"/audit/{entry.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "audit/partials/detail_modal.html")

        ctx_entry = response.context["entry"]
        self.assertEqual(len(ctx_entry.changes_list), 1)
        self.assertEqual(ctx_entry.changes_list[0]["field"], "name")
        self.assertEqual(ctx_entry.changes_list[0]["old"], "Old")
        self.assertEqual(ctx_entry.changes_list[0]["new"], "New")
        self.assertTrue(ctx_entry.serialized_data_pretty)
        self.assertTrue(ctx_entry.additional_data_pretty)
