"""Tests for audit log purging services, functions, and management commands."""
from datetime import timedelta
from io import StringIO

from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.audit.services import purge_old_audit_logs
from apps.users.models import User


class AuditLogPurgeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="auditadmin",
            password="testpassword123",
        )
        self.content_type = ContentType.objects.get_for_model(User)

    def test_purge_old_audit_logs_removes_records_older_than_cutoff(self):
        """Verify purge_old_audit_logs hard deletes records older than cutoff_days and keeps recent ones."""
        now = timezone.now()

        old_entry = LogEntry.objects.create(
            content_type=self.content_type,
            object_pk=str(self.user.pk),
            object_repr=repr(self.user),
            action=LogEntry.Action.UPDATE,
            actor=self.user,
        )
        LogEntry.objects.filter(pk=old_entry.pk).update(timestamp=now - timedelta(days=120))

        recent_entry = LogEntry.objects.create(
            content_type=self.content_type,
            object_pk=str(self.user.pk),
            object_repr=repr(self.user),
            action=LogEntry.Action.UPDATE,
            actor=self.user,
        )
        LogEntry.objects.filter(pk=recent_entry.pk).update(timestamp=now - timedelta(days=10))

        self.assertTrue(LogEntry.objects.filter(pk=old_entry.pk).exists())
        self.assertTrue(LogEntry.objects.filter(pk=recent_entry.pk).exists())

        deleted_count = purge_old_audit_logs(performed_by=self.user, cutoff_days=90)

        self.assertGreaterEqual(deleted_count, 1)
        self.assertFalse(LogEntry.objects.filter(pk=old_entry.pk).exists())
        self.assertTrue(LogEntry.objects.filter(pk=recent_entry.pk).exists())

    def test_purge_audit_logs_management_command(self):
        """Verify python manage.py purge_audit_logs executes and removes stale logs."""
        now = timezone.now()

        old_entry = LogEntry.objects.create(
            content_type=self.content_type,
            object_pk=str(self.user.pk),
            object_repr=repr(self.user),
            action=LogEntry.Action.CREATE,
            actor=self.user,
        )
        LogEntry.objects.filter(pk=old_entry.pk).update(timestamp=now - timedelta(days=100))

        out = StringIO()
        call_command("purge_audit_logs", "--days", "90", stdout=out)
        output = out.getvalue()

        self.assertIn("Successfully purged", output)
        self.assertFalse(LogEntry.objects.filter(pk=old_entry.pk).exists())

    def test_postgresql_fn_purge_old_audit_logs(self):
        """Verify the PostgreSQL function fn_purge_old_audit_logs executes directly in the DB."""
        now = timezone.now()

        old_entry = LogEntry.objects.create(
            content_type=self.content_type,
            object_pk=str(self.user.pk),
            object_repr=repr(self.user),
            action=LogEntry.Action.DELETE,
            actor=self.user,
        )
        LogEntry.objects.filter(pk=old_entry.pk).update(timestamp=now - timedelta(days=150))

        with connection.cursor() as cursor:
            cursor.execute("SELECT fn_purge_old_audit_logs();")
            result = cursor.fetchone()

        self.assertIsNotNone(result)
        self.assertGreaterEqual(result[0], 1)
        self.assertFalse(LogEntry.objects.filter(pk=old_entry.pk).exists())
