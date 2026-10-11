"""Management command to start the APScheduler background runner."""
import logging
import signal
import sys

from django.core.management.base import BaseCommand

from apps.audit.services import run_daily_cleanup_and_maintenance
from apps.core.scheduler import create_scheduler, is_apscheduler_available

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Starts the APScheduler runner to execute daily maintenance jobs (including 1:00 AM PHT cleanup)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--now",
            action="store_true",
            help="Run daily cleanup and maintenance immediately on startup before scheduling.",
        )

    def handle(self, *args, **options):
        if not is_apscheduler_available():
            self.stderr.write(
                self.style.ERROR(
                    "APScheduler is not installed in this environment. "
                    "Install it in production via 'pip install -r requirements/production.txt'."
                )
            )
            return

        if options["now"]:
            self.stdout.write("Running maintenance immediately (--now specified)...")
            res = run_daily_cleanup_and_maintenance()
            self.stdout.write(self.style.SUCCESS(f"Initial run completed: {res}"))

        self.stdout.write("Starting APScheduler (PHT / Asia/Manila, Daily 1:00 AM)...")
        scheduler = create_scheduler(blocking=True)

        if scheduler is None:
            return

        def shutdown_handler(signum, frame):
            self.stdout.write("Received shutdown signal. Stopping scheduler...")
            scheduler.shutdown(wait=False)
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write("Scheduler stopped.")
