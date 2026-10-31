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

    def test_audit_log_pagination_updates_with_action_filter(self):
        """Action filter updates total count and pagination reflecting filtered quantity."""
        from auditlog.models import LogEntry

        ct = ContentType.objects.get_for_model(User)
        # Create 3 update entries and 2 delete entries
        for i in range(3):
            LogEntry.objects.create(
                content_type=ct,
                object_pk=str(self.user.pk),
                object_repr=f"Update {i}",
                action=1,
                actor=self.user,
            )
        for i in range(2):
            LogEntry.objects.create(
                content_type=ct,
                object_pk=str(self.user.pk),
                object_repr=f"Delete {i}",
                action=2,
                actor=self.user,
            )

        # Test action=2 (Delete)
        response = self.client.get("/audit/?action=2", HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        pagination = response.context["pagination"]
        self.assertEqual(pagination["total"], 2)
        self.assertEqual(pagination["total_pages"], 1)
        self.assertEqual(len(response.context["logs"]), 2)
        self.assertEqual(response.context["active_action"], "2")
        self.assertContains(response, "Delete 0")
        self.assertContains(response, "Delete 1")
        self.assertNotContains(response, "Update 0")

    def test_audit_log_pagination_empty_for_zero_results(self):
        """When filter matches zero results, pagination reflects 0 entries and empty page numbers."""
        response = self.client.get("/audit/?q=nonexistent_staff_query_12345", HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        pagination = response.context["pagination"]
        self.assertEqual(pagination["total"], 0)
        self.assertEqual(pagination["total_pages"], 0)
        self.assertEqual(pagination["page_numbers"], [])
        self.assertEqual(pagination["showing_from"], 0)
        self.assertEqual(pagination["showing_to"], 0)

    def test_audit_log_custom_date_range_and_inverted_dates_normalized(self):
        """Custom date range filters entries and normalizes inverted start/end dates."""
        from django.utils import timezone

        today_str = timezone.localdate().strftime("%Y-%m-%d")
        response = self.client.get(
            f"/audit/?range=custom&from=2099-12-31&to={today_str}",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["date_range"], "custom")
        self.assertEqual(response.context["custom_from"], today_str)
        self.assertEqual(response.context["custom_to"], "2099-12-31")
        self.assertGreaterEqual(response.context["pagination"]["total"], 1)
        self.assertContains(response, 'id="audit-active-action"')
        self.assertContains(response, 'id="audit-active-range"')

