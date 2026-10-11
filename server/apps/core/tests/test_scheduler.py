"""Tests for APScheduler integration and daily maintenance tasks."""
from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.audit.services import run_daily_cleanup_and_maintenance
from apps.core import scheduler
from apps.users.models import User


class DailyMaintenanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="scheduleradmin",
            password="securepassword123",
        )
        self.content_type = ContentType.objects.get_for_model(User)

    def test_run_daily_cleanup_and_maintenance_purges_stale_records(self):
        """Verify run_daily_cleanup_and_maintenance hard-deletes logs > 90 days and clears sessions."""
        now = timezone.now()

        # 120-day-old log entry
        old_entry = LogEntry.objects.create(
            content_type=self.content_type,
            object_pk=str(self.user.pk),
            object_repr=repr(self.user),
            action=LogEntry.Action.UPDATE,
            actor=self.user,
        )
        LogEntry.objects.filter(pk=old_entry.pk).update(timestamp=now - timedelta(days=120))

        # Recent entry
        recent_entry = LogEntry.objects.create(
            content_type=self.content_type,
            object_pk=str(self.user.pk),
            object_repr=repr(self.user),
            action=LogEntry.Action.UPDATE,
            actor=self.user,
        )
        LogEntry.objects.filter(pk=recent_entry.pk).update(timestamp=now - timedelta(days=5))

        res = run_daily_cleanup_and_maintenance(performed_by=self.user, audit_log_cutoff_days=90)

        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["audit_logs_purged"], 1)
        self.assertTrue(res["sessions_cleared"])
        self.assertFalse(LogEntry.objects.filter(pk=old_entry.pk).exists())
        self.assertTrue(LogEntry.objects.filter(pk=recent_entry.pk).exists())

    def test_run_maintenance_management_command(self):
        """Verify python manage.py run_maintenance triggers daily cleanup."""
        out = StringIO()
        call_command("run_maintenance", "--audit-days", "90", stdout=out)
        output = out.getvalue()

        self.assertIn("Maintenance completed successfully", output)

    def test_run_scheduler_graceful_missing_apscheduler(self):
        """Verify python manage.py run_scheduler emits a clear error when APScheduler is missing."""
        with patch.object(scheduler, "is_apscheduler_available", return_value=False):
            err = StringIO()
            call_command("run_scheduler", stderr=err)
            self.assertIn("APScheduler is not installed in this environment", err.getvalue())

    def test_schedule_daily_cleanup_job_registration(self):
        """Verify schedule_daily_cleanup_job configures 1:00 AM PHT cron trigger on the scheduler."""
        mock_trigger_cls = MagicMock()
        mock_scheduler = MagicMock()

        with patch.object(scheduler, "APSCHEDULER_INSTALLED", True), \
             patch.object(scheduler, "CronTrigger", mock_trigger_cls):
            scheduler.schedule_daily_cleanup_job(
                mock_scheduler,
                hour=1,
                minute=0,
                timezone_str="Asia/Manila",
            )

            # Assert trigger was instantiated with hour=1, minute=0, and Asia/Manila
            mock_trigger_cls.assert_called_once()
            _, kwargs = mock_trigger_cls.call_args
            self.assertEqual(kwargs["hour"], 1)
            self.assertEqual(kwargs["minute"], 0)
            self.assertEqual(str(kwargs["timezone"]), "Asia/Manila")

            # Assert add_job was called with the job ID and maintenance function
            mock_scheduler.add_job.assert_called_once()
            args, kwargs = mock_scheduler.add_job.call_args
            self.assertEqual(args[0], run_daily_cleanup_and_maintenance)
            self.assertEqual(kwargs["id"], "job_daily_cleanup_and_maintenance")
            self.assertEqual(kwargs["name"], "Daily Database Cleanup & Maintenance (1:00 AM PHT)")
