"""Management command to purge audit log entries older than retention period."""
from django.core.management.base import BaseCommand

from apps.audit.services import purge_old_audit_logs


class Command(BaseCommand):
    help = "Purge audit log records older than a specified number of days (default 90 days)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Number of days to retain audit logs. Default: 90",
        )

    def handle(self, *args, **options):
        days = options["days"]
        self.stdout.write(f"Purging audit log records older than {days} days...")

        class SystemActor:
            id = "system-cli"

        deleted_count = purge_old_audit_logs(performed_by=SystemActor(), cutoff_days=days)
        self.stdout.write(
            self.style.SUCCESS(f"Successfully purged {deleted_count} old audit log record(s).")
        )
