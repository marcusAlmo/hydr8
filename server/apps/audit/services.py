"""Service layer for audit log lifecycle operations.

Handles hard deletion and decongestion of audit logs older than retention windows.
"""
import logging
from datetime import timedelta
from typing import Any

from auditlog.models import LogEntry
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def purge_old_audit_logs(
    *,
    performed_by: Any,
    cutoff_days: int = 90,
) -> int:
    """Delete audit log records older than cutoff_days."""
    cutoff_timestamp = timezone.now() - timedelta(days=cutoff_days)

    with transaction.atomic():
        deleted_count, _ = LogEntry.objects.filter(
            timestamp__lt=cutoff_timestamp
        ).delete()

    actor_id = getattr(performed_by, "id", None) or "system"
    logger.info(
        "[%s] Hard-deleted old audit log records older than %d days. deleted_count=%d",
        actor_id,
        cutoff_days,
        deleted_count,
    )
    return deleted_count


def run_daily_cleanup_and_maintenance(
    *,
    performed_by: Any = None,
    audit_log_cutoff_days: int = 90,
) -> dict[str, Any]:
    """Run daily maintenance: purge stale audit logs and clear expired sessions."""
    from django.core.management import call_command

    actor = performed_by
    if actor is None:
        class SystemActor:
            id = "system-maintenance-cron"

        actor = SystemActor()

    actor_id = getattr(actor, "id", None) or "system"
    logger.info("[%s] Initiating daily system cleanup and maintenance...", actor_id)

    # Purge stale audit log records
    purged_audit_count = purge_old_audit_logs(
        performed_by=actor,
        cutoff_days=audit_log_cutoff_days,
    )

    # Clear expired sessions
    try:
        call_command("clearsessions")
        sessions_cleared = True
    except Exception as exc:
        logger.warning("[%s] clearsessions encountered an error: %s", actor_id, exc)
        sessions_cleared = False

    logger.info(
        "[%s] Completed daily system cleanup and maintenance. audit_logs_purged=%d, sessions_cleared=%s",
        actor_id,
        purged_audit_count,
        sessions_cleared,
    )

    return {
        "status": "SUCCESS",
        "audit_logs_purged": purged_audit_count,
        "sessions_cleared": sessions_cleared,
    }
