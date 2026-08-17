import logging
import secrets
import string
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.users.models import Role, User

logger = logging.getLogger(__name__)

# Lockout policy — 5 failed attempts locks the (ip, username) bucket for 1 minute.
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 60

# Temporary password policy — 12 chars, mixed case + digits + symbols.
TEMP_PASSWORD_LENGTH = 12
_TEMP_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*"


def generate_temporary_password(*, length: int = TEMP_PASSWORD_LENGTH) -> str:
    """
    Generates a cryptographically secure temporary password.
    Uses ``secrets`` (not ``random``) to ensure CSPRNG-grade entropy.
    Guarantees at least one uppercase, one lowercase, one digit, and one symbol.
    """
    while True:
        pw = "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(length))
        has_upper = any(c.isupper() for c in pw)
        has_lower = any(c.islower() for c in pw)
        has_digit = any(c.isdigit() for c in pw)
        has_symbol = any(c in "!@#$%^&*" for c in pw)
        if has_upper and has_lower and has_digit and has_symbol:
            return pw


def set_temporary_password(*, user: User) -> str:
    """
    Generates a temporary password, sets it as the user's password, and
    flags the account for a forced password change on next login.

    Returns the raw (plaintext) temporary password so the caller can display
    it once for copy. The plaintext is never logged or persisted.

    Logs only the user ID — never the password itself (RA 10173).
    """
    raw_password = generate_temporary_password()
    user.set_password(raw_password)
    user.force_password_change = True
    user.save(update_fields=["password", "password_expires_at", "force_password_change", "updated_at"])
    logger.info(
        "Temporary password generated. user_id=%s force_change=True",
        user.id,
    )
    return raw_password


def create_user_account(
    *,
    username: str,
    first_name: str,
    last_name: str,
    email: str,
    role: Role,
    company_id: int | None,
    performed_by,
    daily_rate: Decimal | str | None = None,
) -> User:
    """
    Creates a new active user in the same tenant as the requester,
    assigns the requested role, and flags them for onboarding.
    The caller is expected to set a temporary password immediately.

    ``daily_rate`` is stored only for Staff role users; it is ignored
    for other roles (drivers are commission-based, admins have no rate).
    """
    if User.objects.filter(username=username, deleted_at__isnull=True).exists():
        raise ValidationError("A user with that username already exists.")

    # Parse and validate the daily rate for Staff users.
    rate_value = Decimal("0.00")
    if role.name == "Staff" and daily_rate not in (None, ""):
        try:
            rate_value = Decimal(str(daily_rate))
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError("Daily rate must be a valid decimal number.") from exc
        if rate_value < 0:
            raise ValidationError("Daily rate cannot be negative.")

    with transaction.atomic():
        user = User(
            username=username,
            first_name=first_name or "",
            last_name=last_name or "",
            email=email or "",
            role=role,
            company_id=company_id,
            is_active=True,
            is_staff=(role.name in ("Admin", "Staff")),
            daily_rate=rate_value if role.name == "Staff" else Decimal("0.00"),
        )
        user.set_unusable_password()
        try:
            user.save()
        except IntegrityError as exc:
            raise ValidationError("A user with that username already exists.") from exc

    logger.info("[%s] Created User id=%s", performed_by.id, user.id)
    return user


def change_user_password(*, user: User, new_password: str) -> None:
    """
    Sets a new password for the user and clears the force_password_change flag.
    Used by the forced password-change flow after a temporary-password login.
    """
    user.set_password(new_password)
    user.force_password_change = False
    user.save(update_fields=["password", "password_expires_at", "force_password_change", "updated_at"])
    logger.info(
        "Password changed by user. user_id=%s force_change=False",
        user.id,
    )


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
    redacted_username = f"{username[:1]}***" if username else ""
    logger.warning(
        "Failed login attempt. ip=%s username_hint=%s attempts=%s",
        ip, redacted_username, attempts,
    )


def reset_failed_login(*, ip: str, username: str) -> None:
    """Clears the failed-attempt counter on a successful login."""
    cache.delete(_lockout_cache_key(ip, username))


def get_client_ip(*, request) -> str:
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


def onboard_user(*, user: User, new_password: str, new_pin: str) -> None:
    """
    Sets the user's password and PIN during first-time onboarding.
    Clears the force_password_change flag.
    """
    user.set_password(new_password)
    user.set_pin(new_pin)
    user.force_password_change = False
    user.save(update_fields=["password", "password_expires_at", "pin", "pin_expires_at", "force_password_change", "updated_at"])
    logger.info("User onboarded. user_id=%s", user.id)


def validate_user_pin(
    *,
    user: User,
    pin: str | None,
    required_message: str = "PIN is required.",
) -> None:
    """
    Standardized, reusable PIN validator for sensitive operations.

    Verifies that:
      1. The user has an active, configured PIN.
      2. The PIN input is non-empty.
      3. The provided PIN matches the stored hash via user.check_pin.

    Raises:
        ValidationError: If PIN is unconfigured, missing, or incorrect.
    """
    raw_pin = (pin or "").strip()
    if not getattr(user, "pin", None):
        raise ValidationError(
            "No PIN is configured for your account. Please set a PIN in your profile first."
        )
    if not raw_pin:
        raise ValidationError(required_message)
    if not user.check_pin(raw_pin):
        raise ValidationError("Incorrect PIN.")


# ---------------------------------------------------------------------------
# Soft-delete — admin action on the edit user form.
# ---------------------------------------------------------------------------

# Delete-confirmation challenge — exactly 8 alphanumeric characters.
DELETE_CHALLENGE_LENGTH = 8
_DELETE_CHALLENGE_ALPHABET = string.ascii_letters + string.digits


def generate_delete_challenge() -> str:
    """
    Generates a cryptographically-secure 8-character alphanumeric challenge
    string. The user must retype this exact code to confirm a destructive
    delete operation, adding friction against accidental deletion.
    """
    return "".join(
        secrets.choice(_DELETE_CHALLENGE_ALPHABET)
        for _ in range(DELETE_CHALLENGE_LENGTH)
    )


def soft_delete_user(*, user: User, performed_by) -> None:
    """
    Soft-deletes a user by setting ``deleted_at`` to the current timestamp
    and deactivating the account. The row is preserved for audit/history;
    all read-side selectors filter ``deleted_at__isnull=True`` so the user
    disappears from the directory, search, suggestions, and rider lists.

    Raises ``ValidationError`` if the user is already soft-deleted or if the
    actor attempts to delete their own account.
    """
    if user.deleted_at is not None:
        raise ValidationError("This user has already been deleted.")
    if performed_by.pk == user.pk:
        raise ValidationError("You cannot delete your own account.")

    user.deleted_at = timezone.now()
    user.is_active = False
    user.save(update_fields=["deleted_at", "is_active", "updated_at"])
    logger.info("[%s] Soft-deleted User id=%s", performed_by.id, user.id)
