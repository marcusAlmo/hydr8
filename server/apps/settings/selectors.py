"""Read-side selectors for the Settings page.

The Settings page has three tabs (System Config, Company, My Profile).
Each tab consumes a different slice of data:

  * System Config — key/value rows from ``core.SystemConfig`` enriched
    with UI metadata (label, description, widget type, options).
  * Company       — the tenant's ``settings.Company`` row.
  * My Profile    — the logged-in user's ``User`` record.

These selectors return plain dicts shaped to match the existing mock
context so the templates need minimal changes.  No business logic lives
here — only reads + formatting.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.utils import timezone

from apps.core.models import SystemConfig
from apps.users.permissions import is_staff_role

# ---------------------------------------------------------------------------
# UI metadata for System Config keys.
#
# This is static, compile-time-known display configuration — it belongs in
# code, not in the database.  Each entry describes how a raw SystemConfig
# value is rendered and edited in the System Config tab.
# ---------------------------------------------------------------------------
# Widget types: "select" (dropdown) or "number" (text input).
# "highlight": True draws the border-t-2 accent for financial/operational
# ceilings (matches the original mock styling).
SYSTEM_CONFIG_METADATA: dict[str, dict[str, Any]] = {
    'lockscreen_timeout_minutes': {
        'label': 'Lockscreen Timeout',
        'description': 'Minutes of inactivity before force logout.',
        'type': 'select',
        'options': ['5 min', '15 min', '30 min', 'Never'],
        'highlight': False,
    },
    'tithe_rate': {
        'label': 'Tithe Rate (%)',
        'description': 'Percentage of net profit allocated to tithes.',
        'type': 'number',
        'highlight': True,  # financial setting
    },
    'approved_credit_limit': {
        'label': 'Approved Credit Limit (₱)',
        'description': 'Maximum outstanding debt a customer can accrue '
                       'before further credit is blocked.',
        'type': 'number',
        'highlight': True,  # financial setting
    },
    'approved_container_limit': {
        'label': 'Approved Container Borrowing Limit',
        'description': 'Maximum total containers (round + slim + other) '
                       'a customer may have unreturned at once.',
        'type': 'number',
        'highlight': True,  # operational ceiling
    },
    'overdue_threshold_days': {
        'label': 'Overdue Threshold (days)',
        'description': 'Number of days after which an unpaid credit or '
                       'unreturned container is considered overdue. '
                       'Drives the "Action required" indicator on customer '
                       'profiles and the debt-management severity styling.',
        'type': 'number',
        'highlight': True,  # operational threshold
    },
}

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

# Mapping between raw lockscreen minutes and the display select options.
# "Never" is represented as 0 minutes internally.
_LOCKSCREEN_DISPLAY_TO_RAW = {
    '5 min': '5',
    '15 min': '15',
    '30 min': '30',
    'Never': '0',
}
_LOCKSCREEN_RAW_TO_DISPLAY = {v: k for k, v in _LOCKSCREEN_DISPLAY_TO_RAW.items()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_config_value(key: str, company_id: int | None) -> str:
    """Reads a SystemConfig value, preferring the tenant-scoped row.

    Falls back to the global (company=NULL) row, then to the hardcoded
    default.  Never raises — the Settings page must always render.
    """
    # Try tenant-scoped first.
    qs = SystemConfig.objects.filter(key=key)
    if company_id is not None:
        row = qs.filter(company_id=company_id).first()
        if row is not None:
            return row.value
    # Fall back to global.
    row = qs.filter(company_id__isnull=True).first()
    if row is not None:
        return row.value
    # Final fallback — hardcoded default.
    return SYSTEM_CONFIG_DEFAULTS.get(key, '')


def _format_tithe_rate_display(raw: str) -> str:
    """Converts the stored decimal fraction (0.10) to a percentage (10.00)."""
    try:
        return f"{(Decimal(raw) * 100).quantize(Decimal('0.01'))}"
    except (InvalidOperation, ValueError):
        return '10.00'


def _format_currency_display(raw: str) -> str:
    """Converts a raw numeric string (3000.00) to a grouped display (3,000.00)."""
    try:
        dec = Decimal(raw).quantize(Decimal('0.01'))
        return f"{dec:,.2f}"
    except (InvalidOperation, ValueError):
        return raw


def _format_lockscreen_display(raw: str) -> str:
    """Converts raw minutes (5) to the select-option label (5 min)."""
    return _LOCKSCREEN_RAW_TO_DISPLAY.get(raw, f"{raw} min")


def _format_system_config_row(key: str, raw_value: str) -> dict[str, Any]:
    """Builds a single System Config tab row from a raw value + metadata."""
    meta = SYSTEM_CONFIG_METADATA[key]
    # Format the display value based on the key.
    if key == 'tithe_rate':
        display_value = _format_tithe_rate_display(raw_value)
    elif key == 'approved_credit_limit':
        display_value = _format_currency_display(raw_value)
    elif key == 'lockscreen_timeout_minutes':
        display_value = _format_lockscreen_display(raw_value)
    else:
        display_value = raw_value

    return {
        'key': key,
        'label': meta['label'],
        'description': meta['description'],
        'type': meta['type'],
        'value': display_value,
        'options': meta.get('options', []),
        'highlight': meta['highlight'],
        # The raw value is carried alongside so the save service can
        # compare dirty state without re-parsing the display string.
        'raw_value': raw_value,
    }


def _build_system_config(company_id: int | None) -> list[dict[str, Any]]:
    """Builds the list of System Config rows in display order."""
    rows = []
    for key in (
        'lockscreen_timeout_minutes',
        'tithe_rate',
        'approved_credit_limit',
        'approved_container_limit',
        'overdue_threshold_days',
    ):
        raw = _get_config_value(key, company_id)
        rows.append(_format_system_config_row(key, raw))
    return rows


def _build_company_context(user) -> dict[str, str]:
    """Builds the Company tab context from the user's tenant."""
    company = getattr(user, 'company', None)
    if company is None:
        # Platform superuser with no tenant — return empty strings so the
        # form renders blank rather than crashing.
        return {
            'name': '',
            'contact_number': '',
            'email': '',
            'address': '',
            'has_company': False,
        }
    return {
        'name': company.name or '',
        'contact_number': company.contact_number or '',
        'email': company.email or '',
        'address': company.address or '',
        'has_company': True,
    }


def _build_profile_context(user) -> dict[str, str]:
    """Builds the My Profile tab context from the logged-in user."""
    first = user.first_name or ''
    last = user.last_name or ''
    initials = ''
    if first and last:
        initials = (first[0] + last[0]).upper()
    elif user.username:
        initials = user.username[:2].upper()

    role_name = ''
    if getattr(user, 'role', None) is not None:
        role_name = user.role.name or ''

    return {
        'username': user.username or '',
        'first_name': first,
        'last_name': last,
        'full_name': user.full_name,
        'role': role_name,
        'avatar_initials': initials,
    }


# ---------------------------------------------------------------------------
# Public selector — returns the full Settings page context.
# ---------------------------------------------------------------------------

# Tab definitions are static — identical to the original mock.
_SETTINGS_TABS = [
    {'id': 'system-config', 'label': 'System Config', 'icon': 'tune', 'active': True},
    {'id': 'company', 'label': 'Company', 'icon': 'business', 'active': False},
    {'id': 'profile', 'label': 'My Profile', 'icon': 'account_circle', 'active': False},
]


def get_settings_context(user) -> dict[str, Any]:
    """Returns the full context dict consumed by ``settings/settings.html``.

    Replaces the former ``_mock_settings_data`` helper.  The shape is
    identical so the templates need no structural changes — only the
    values are now sourced from the database.

    For Staff users, only the My Profile tab is exposed — system config
    and company settings are Admin-only.
    """
    company_id = getattr(getattr(user, 'company', None), 'id', None)

    if is_staff_role(user):
        tabs = [t for t in _SETTINGS_TABS if t['id'] == 'profile']
    else:
        tabs = _SETTINGS_TABS

    return {
        'today_date': timezone.localtime().strftime('%A, %b %d, %Y'),
        'tabs': tabs,
        'system_config': _build_system_config(company_id),
        'company': _build_company_context(user),
        'profile': _build_profile_context(user),
    }


# ---------------------------------------------------------------------------
# Domain helpers — read individual config values for use by other apps.
# ---------------------------------------------------------------------------

def get_overdue_threshold_days(user) -> int:
    """Returns the configured overdue threshold in days for the user's tenant.

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
    """Returns the configured lockscreen idle timeout in minutes.

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
    """Returns the tenant's default approved credit limit for new customers.

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
