"""Management command to manually run daily cleanup and maintenance."""
from django.core.management.base import BaseCommand

from apps.audit.services import run_daily_cleanup_and_maintenance


class Command(BaseCommand):
    help = "Manually triggers daily station cleanup and maintenance (purges audit logs > 3 months, clears sessions)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--audit-days",
            type=int,
            default=90,
            help="Number of days of audit logs to retain. Default: 90",
        )

    def handle(self, *args, **options):
        days = options["audit_days"]
        self.stdout.write(f"Executing system maintenance (audit log cutoff: {days} days)...")

        class CliActor:
            id = "system-maintenance-cli"

        result = run_daily_cleanup_and_maintenance(performed_by=CliActor(), audit_log_cutoff_days=days)
        self.stdout.write(
            self.style.SUCCESS(
                f"Maintenance completed successfully: "
                f"audit_logs_purged={result.get('audit_logs_purged')}, "
                f"sessions_cleared={result.get('sessions_cleared')}"
            )
        )
