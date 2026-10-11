"""Background task scheduling with APScheduler.

Registers periodic maintenance tasks including daily session cleanup and audit log purging.
Imports APScheduler defensively so environments without the package installed
continue to run without errors.
"""
import logging
from typing import Any
from zoneinfo import ZoneInfo

from apps.audit.services import run_daily_cleanup_and_maintenance

logger = logging.getLogger(__name__)

JOB_DAILY_CLEANUP_ID = "job_daily_cleanup_and_maintenance"

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    APSCHEDULER_INSTALLED = True
except ImportError:
    BackgroundScheduler = None  # type: ignore[assignment,misc]
    BlockingScheduler = None  # type: ignore[assignment,misc]
    CronTrigger = None  # type: ignore[assignment,misc]
    APSCHEDULER_INSTALLED = False


def is_apscheduler_available() -> bool:
    """Return True if APScheduler is installed in the current environment."""
    return APSCHEDULER_INSTALLED


def schedule_daily_cleanup_job(
    scheduler: Any,
    *,
    hour: int = 1,
    minute: int = 0,
    timezone_str: str = "Asia/Manila",
) -> Any:
    """Register the daily cleanup and maintenance job on the scheduler.

    Runs daily at 1:00 AM PHT to prune audit logs older than retention cutoff
    and clear expired user sessions.
    """
    if not APSCHEDULER_INSTALLED or CronTrigger is None:
        logger.warning(
            "Cannot schedule daily cleanup: APScheduler is not installed in this environment."
        )
        return None

    tz = ZoneInfo(timezone_str)
    trigger = CronTrigger(hour=hour, minute=minute, timezone=tz)

    job = scheduler.add_job(
        run_daily_cleanup_and_maintenance,
        trigger=trigger,
        id=JOB_DAILY_CLEANUP_ID,
        name="Daily Database Cleanup & Maintenance (1:00 AM PHT)",
        replace_existing=True,
    )

    logger.info(
        "Registered APScheduler job '%s' scheduled daily at %02d:%02d (%s)",
        JOB_DAILY_CLEANUP_ID,
        hour,
        minute,
        timezone_str,
    )
    return job


def create_scheduler(*, blocking: bool = False, timezone_str: str = "Asia/Manila") -> Any | None:
    """Instantiate and configure an APScheduler instance."""
    if not APSCHEDULER_INSTALLED:
        logger.warning("APScheduler is not installed in this environment.")
        return None

    tz = ZoneInfo(timezone_str)
    scheduler_cls = BlockingScheduler if blocking else BackgroundScheduler
    scheduler = scheduler_cls(timezone=tz)

    # Register daily cleanup job for 1:00 AM PHT
    schedule_daily_cleanup_job(scheduler, hour=1, minute=0, timezone_str=timezone_str)

    return scheduler
