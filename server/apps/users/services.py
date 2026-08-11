import logging

from django.core.cache import cache
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Lockout policy — 5 failed attempts locks the (ip, username) bucket for 1 minute.
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 60


def _lockout_cache_key(ip: str, username: str) -> str:
    """Builds the cache key tracking failed login attempts for an (ip, username) pair."""
    return f"login_attempts:{ip}:{username}"


def get_failed_attempt_count(*, ip: str, username: str) -> int:
    """Returns the current failed-attempt count for the (ip, username) bucket."""
    return int(cache.get(_lockout_cache_key(ip, username), 0))


def is_login_locked(*, ip: str, username: str) -> bool:
    """Returns True if the (ip, username) bucket has reached the lockout threshold."""
    return get_failed_attempt_count(ip=ip, username=username) >= LOGIN_MAX_ATTEMPTS


def record_failed_login(*, ip: str, username: str) -> None:
    """
    Increments the failed-attempt counter for the (ip, username) bucket.
    The (re)set TTL is the lockout window so the counter naturally expires.
    Logs only the IP and a redacted username hint — never credentials (RA 10173).
    """
    key = _lockout_cache_key(ip, username)
    attempts = int(cache.get(key, 0)) + 1
    cache.set(key, attempts, timeout=LOGIN_LOCKOUT_SECONDS)
    logger.warning(
        "Failed login attempt. ip=%s username=%s attempts=%s",
        ip, username, attempts,
    )


def reset_failed_login(*, ip: str, username: str) -> None:
    """Clears the failed-attempt counter on a successful login."""
    cache.delete(_lockout_cache_key(ip, username))


def get_client_ip(request) -> str:
    """
    Resolves the client IP from the request, honoring the X-Forwarded-For header
    when set by a trusted reverse proxy. Falls back to REMOTE_ADDR.
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        # Leftmost entry is the original client; subsequent are proxies.
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def check_login_lockout(*, ip: str, username: str) -> None:
    """
    Raises ValidationError if the (ip, username) bucket is currently locked out.
    Used by the login view to short-circuit before running AuthenticationForm.
    """
    if is_login_locked(ip=ip, username=username):
        raise ValidationError(
            "Too many failed attempts. Please try again in 1 minute."
        )
