"""Read-side selectors for the Settings page.

Selectors read raw SystemConfig values from the database and provide
domain helpers for other apps. All template-shaped formatting (display
strings, tab dicts, card shaping) lives in ``presentation_settings.py``.
Views compose selectors with presentation functions.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from apps.core.models import SystemConfig

# Raw default values used when a key is missing from the DB (defensive —
# the seed migration should have created them, but we never want the
# Settings page to crash because a row is absent).
SYSTEM_CONFIG_DEFAULTS: dict[str, str] = {
    'lockscreen_timeout_minutes': '5',
    'tithe_rate': '0.10',
    'approved_credit_limit': '3000.00',
    'approved_container_limit': '20',
    'overdue_threshold_days': '7',
}

# All SystemConfig keys that the Settings page reads and displays.
SETTINGS_CONFIG_KEYS = (
    'lockscreen_timeout_minutes',
    'tithe_rate',
    'approved_credit_limit',
    'approved_container_limit',
    'overdue_threshold_days',
)


def _get_config_value(key: str, company_id: int | None) -> str:
    """Read a SystemConfig value, preferring the tenant-scoped row.

    Falls back to the global (company=NULL) row, then to the hardcoded
    default.  Never raises — the Settings page must always render.
    """
    qs = SystemConfig.objects.filter(key=key)
    if company_id is not None:
        row = qs.filter(company_id=company_id).first()
        if row is not None:
            return row.value
    row = qs.filter(company_id__isnull=True).first()
    if row is not None:
        return row.value
    return SYSTEM_CONFIG_DEFAULTS.get(key, '')


def get_all_config_values(company_id: int | None) -> dict[str, str]:
    """Return all SystemConfig values for the Settings page.

    Returns a dict of {key: raw_value} for all keys in
    ``SETTINGS_CONFIG_KEYS``.
    """
    return {key: _get_config_value(key, company_id) for key in SETTINGS_CONFIG_KEYS}


# ---------------------------------------------------------------------------
# Domain helpers — read individual config values for use by other apps.
# These stay in selectors because they are query functions, not
# presentation logic. Other apps import them directly.
# ---------------------------------------------------------------------------

def get_overdue_threshold_days(user) -> int:
    """Return the configured overdue threshold in days for the user's tenant.

    Reads the ``overdue_threshold_days`` SystemConfig key, preferring the
    tenant-scoped row, then the global row, then the hardcoded default (7).
    Never raises — callers can use this directly in selectors.
    """
    company_id = getattr(getattr(user, 'company', None), 'id', None)
    raw = _get_config_value('overdue_threshold_days', company_id)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = int(SYSTEM_CONFIG_DEFAULTS['overdue_threshold_days'])
    return val if val > 0 else 1


def get_lockscreen_timeout_minutes(user) -> int:
    """Return the configured lockscreen idle timeout in minutes.

    Reads the ``lockscreen_timeout_minutes`` SystemConfig key, preferring
    the tenant-scoped row, then the global row, then the hardcoded default
    (5).  A value of ``0`` means "Never" — the lock screen is disabled.

    Never raises — callers can use this directly.  Returns ``0`` when the
    timeout is disabled.
    """
    company_id = getattr(getattr(user, 'company', None), 'id', None)
    raw = _get_config_value('lockscreen_timeout_minutes', company_id)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = int(SYSTEM_CONFIG_DEFAULTS['lockscreen_timeout_minutes'])
    return max(val, 0)


def get_default_credit_limit(user) -> Decimal:
    """Return the tenant's default approved credit limit for new customers.

    Reads the ``approved_credit_limit`` SystemConfig key, preferring the
    tenant-scoped row, then the global row, then the hardcoded default
    (3000.00).  Used to pre-populate the Add Customer modal so operators
    don't have to re-enter the same ceiling for every customer — they can
    still override it per customer at creation time.

    Never raises — callers can use this directly.  Returns a non-negative
    ``Decimal`` quantized to two decimal places.
    """
    company_id = getattr(getattr(user, 'company', None), 'id', None)
    raw = _get_config_value('approved_credit_limit', company_id)
    try:
        dec = Decimal(raw).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        dec = Decimal(SYSTEM_CONFIG_DEFAULTS['approved_credit_limit'])
    return dec if dec >= 0 else Decimal('0.00')
