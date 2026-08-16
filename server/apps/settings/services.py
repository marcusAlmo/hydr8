"""Write-side services for the Settings page.

Each service is a plain keyword-only function that performs a single
mutation, validates input, and raises ``ValidationError`` on violations.
Views call these services — they never write to the ORM directly.

Financial integrity note
------------------------
``tithe_rate`` is read by the remittance finalize service as
``Decimal(SystemConfig.objects.get_value('tithe_rate', '0.10'))`` and
multiplied by ``net_profit``.  The stored value MUST be a decimal
fraction (0.10), NOT a display percentage (10.00).  ``save_system_config``
performs the display→raw conversion and validates the range [0, 1].
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.models import SystemConfig
from apps.settings.models import Company
from apps.settings.selectors import _LOCKSCREEN_DISPLAY_TO_RAW

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System Config
# ---------------------------------------------------------------------------

def _parse_display_value(key: str, display_value: str) -> str:
    """Converts a display value back to the raw storage format.

    This is the inverse of the formatting in ``selectors.py``.  Any
    conversion error raises ``ValidationError`` so the view can re-render
    the form with a friendly message.
    """
    raw = (display_value or '').strip()

    if key == 'lockscreen_timeout_minutes':
        # The select widget submits the display label ("5 min", "Never").
        if raw in _LOCKSCREEN_DISPLAY_TO_RAW:
            return _LOCKSCREEN_DISPLAY_TO_RAW[raw]
        # Allow a raw integer through as well (defensive).
        if raw.isdigit():
            return raw
        raise ValidationError(
            "Lockscreen timeout must be one of: 5 min, 15 min, 30 min, Never."
        )

    if key == 'tithe_rate':
        # Display is a percentage (10.00); storage is a fraction (0.10).
        try:
            pct = Decimal(raw)
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError("Tithe rate must be a number.") from exc
        if pct < 0 or pct > 100:
            raise ValidationError("Tithe rate must be between 0 and 100.")
        fraction = (pct / Decimal('100')).quantize(Decimal('0.0001'))
        return str(fraction)

    if key == 'approved_credit_limit':
        # Display is grouped currency (3,000.00); storage is raw decimal.
        cleaned = raw.replace(',', '').replace('₱', '').strip()
        try:
            dec = Decimal(cleaned)
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError("Credit limit must be a number.") from exc
        if dec < 0:
            raise ValidationError("Credit limit cannot be negative.")
        return str(dec.quantize(Decimal('0.01')))

    if key == 'approved_container_limit':
        if not raw.isdigit():
            raise ValidationError("Container limit must be a whole number.")
        val = int(raw)
        if val < 0:
            raise ValidationError("Container limit cannot be negative.")
        return str(val)

    if key == 'overdue_threshold_days':
        if not raw.isdigit():
            raise ValidationError("Overdue threshold must be a whole number of days.")
        val = int(raw)
        if val < 1:
            raise ValidationError("Overdue threshold must be at least 1 day.")
        return str(val)

    # Unknown key — store as-is (no conversion).
    return raw


@transaction.atomic
def save_system_config(*, key: str, display_value: str, performed_by) -> SystemConfig:
    """Updates a single SystemConfig row from a display-formatted value.

    Resolves the tenant-scoped row (``performed_by.company``) if one
    exists, otherwise the global row (``company=NULL``).  Creates the
    row if it is missing.  Sets ``updated_by`` for the audit trail.

    Raises ``ValidationError`` if the display value cannot be parsed or
    is out of range.
    """
    if key not in (
        'lockscreen_timeout_minutes', 'tithe_rate',
        'approved_credit_limit', 'approved_container_limit',
        'overdue_threshold_days',
    ):
        raise ValidationError(f"Unknown system config key: {key}")

    raw_value = _parse_display_value(key, display_value)
    company = getattr(performed_by, 'company', None)

    # update_or_create is safe under the unique_systemconfig_company_key
    # constraint.  We filter on (company, key) so we hit the right row.
    obj, created = SystemConfig.objects.update_or_create(
        company=company,
        key=key,
        defaults={
            'value': raw_value,
            'updated_by': performed_by,
        },
    )

    logger.info(
        "SystemConfig saved. key=%s raw=%s actor=%s company_id=%s created=%s",
        key, raw_value, performed_by.id,
        getattr(company, 'id', None), created,
    )
    return obj


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

@transaction.atomic
def save_company(*, user, name: str, contact_number: str,
                 email: str, address: str) -> Company:
    """Updates the tenant Company row for the given user.

    Raises ``ValidationError`` if the user has no tenant (platform
    superuser) or the name is empty.
    """
    company = getattr(user, 'company', None)
    if company is None:
        raise ValidationError(
            "Your account is not associated with a company. "
            "Platform superusers cannot edit company details."
        )

    name = (name or '').strip()
    if not name:
        raise ValidationError("Company name is required.")

    company.name = name
    company.contact_number = (contact_number or '').strip() or None
    company.email = (email or '').strip() or None
    company.address = (address or '').strip() or None
    company.save(update_fields=[
        'name', 'contact_number', 'email', 'address', 'updated_at',
    ])

    logger.info(
        "Company saved. company_id=%s actor=%s",
        company.id, user.id,
    )
    return company


# ---------------------------------------------------------------------------
# Profile (name fields)
# ---------------------------------------------------------------------------

@transaction.atomic
def update_profile(*, user, first_name: str, last_name: str) -> None:
    """Updates the logged-in user's first and last name.

    These are self-service fields.  Username and password changes have
    their own services (below) with current-password verification.
    """
    user.first_name = (first_name or '').strip()
    user.last_name = (last_name or '').strip()
    user.save(update_fields=['first_name', 'last_name', 'updated_at'])

    logger.info("Profile name updated. user_id=%s", user.id)


# ---------------------------------------------------------------------------
# Username change (current-password verified)
# ---------------------------------------------------------------------------

@transaction.atomic
def change_username(*, user, current_password: str, new_username: str) -> None:
    """Changes the user's username after verifying the current password.

    Raises ``ValidationError`` if the current password is wrong, the
    new username is blank, or it is already taken by another user.
    """
    if not user.check_password(current_password or ''):
        raise ValidationError("Your current password is incorrect.")

    new_username = (new_username or '').strip()
    if not new_username:
        raise ValidationError("Username cannot be empty.")

    from django.contrib.auth import get_user_model
    User = get_user_model()

    if User.objects.filter(username__iexact=new_username).exclude(pk=user.pk).exists():
        raise ValidationError("That username is already taken.")

    user.username = new_username
    user.save(update_fields=['username', 'updated_at'])

    logger.info("Username changed. user_id=%s", user.id)


# ---------------------------------------------------------------------------
# Password change (current-password verified)
# ---------------------------------------------------------------------------

@transaction.atomic
def change_password(*, user, current_password: str, new_password: str) -> None:
    """Changes the user's password after verifying the current password.

    Distinct from ``apps.users.services.change_user_password`` (which is
    used for the forced post-temp-login flow and does NOT verify the
    current password).  This service is for self-service password changes
    from the Settings page, where the user must prove they know the
    current password.

    Raises ``ValidationError`` if the current password is wrong or the
    new password is shorter than 8 characters.
    """
    if not user.check_password(current_password or ''):
        raise ValidationError("Your current password is incorrect.")

    if not new_password or len(new_password) < 8:
        raise ValidationError("New password must be at least 8 characters.")

    user.set_password(new_password)
    user.force_password_change = False
    user.save(update_fields=['password', 'force_password_change', 'updated_at'])

    logger.info("Password changed (self-service). user_id=%s", user.id)
    return user
