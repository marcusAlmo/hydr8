"""Signal handlers that record ACCESS events in the audit log.

Connected in AuditConfig.ready(). Handles:
  - user_logged_in  -> LogEntry(action=ACCESS, additional_data={"event": "login", ...})
  - user_logged_out -> LogEntry(action=ACCESS, additional_data={"event": "logout", ...})
  - login_failed    -> LogEntry(action=ACCESS, additional_data={"event": "login_failed", ...})

All handlers swallow exceptions -- audit logging must never break the login flow.
"""
import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.contenttypes.models import ContentType
from django.dispatch import receiver

from auditlog.cid import get_cid
from auditlog.models import LogEntry

from apps.users.models import User
from apps.users.signals import login_failed

logger = logging.getLogger(__name__)


def _get_request_meta(request) -> dict:
    """Extracts remote_addr and user_agent from the request."""
    meta = {"remote_addr": None, "user_agent": ""}
    if not request:
        return meta
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        meta["remote_addr"] = xff.split(",")[0].strip()
    else:
        meta["remote_addr"] = request.META.get("REMOTE_ADDR")
    meta["user_agent"] = request.META.get("HTTP_USER_AGENT", "")
    return meta


def _get_session_key(request) -> str | None:
    return request.session.session_key if request else None


@receiver(user_logged_in)
def _log_login(sender, request, user, **kwargs):
    """Creates an ACCESS LogEntry when a user logs in."""
    try:
        ct = ContentType.objects.get_for_model(User)
        meta = _get_request_meta(request)
        LogEntry.objects.create(
            content_type=ct,
            object_pk=str(user.pk),
            object_repr=str(user),
            action=LogEntry.Action.ACCESS,
            changes={},
            actor=user,
            actor_email=user.email,
            cid=get_cid(),
            remote_addr=meta["remote_addr"],
            additional_data={
                "event": "login",
                "session_key": _get_session_key(request),
                "device_name": meta["user_agent"],
                "ip_address": meta["remote_addr"],
            },
        )
    except Exception:
        logger.exception("Failed to log login event for user_id=%s", user.id)


@receiver(user_logged_out)
def _log_logout(sender, request, user, **kwargs):
    """Creates an ACCESS LogEntry when a user logs out."""
    if user is None:
        return
    try:
        ct = ContentType.objects.get_for_model(User)
        meta = _get_request_meta(request)
        LogEntry.objects.create(
            content_type=ct,
            object_pk=str(user.pk),
            object_repr=str(user),
            action=LogEntry.Action.ACCESS,
            changes={},
            actor=user,
            actor_email=user.email,
            cid=get_cid(),
            remote_addr=meta["remote_addr"],
            additional_data={
                "event": "logout",
                "session_key": _get_session_key(request),
                "device_name": meta["user_agent"],
                "ip_address": meta["remote_addr"],
            },
        )
    except Exception:
        logger.exception("Failed to log logout event for user_id=%s", user.id)


@receiver(login_failed)
def _log_login_failed(sender, request, username, ip, **kwargs):
    """Creates an ACCESS LogEntry when a login attempt fails."""
    try:
        ct = ContentType.objects.get_for_model(User)
        meta = _get_request_meta(request)
        LogEntry.objects.create(
            content_type=ct,
            object_pk="unknown",
            object_repr=f"Failed login: username='{username}'",
            action=LogEntry.Action.ACCESS,
            changes={},
            actor=None,
            actor_email=None,
            cid=get_cid(),
            remote_addr=ip or meta["remote_addr"],
            additional_data={
                "event": "login_failed",
                "username": username,
                "ip_address": ip or meta["remote_addr"],
            },
        )
    except Exception:
        logger.exception("Failed to create failed-login audit record")
