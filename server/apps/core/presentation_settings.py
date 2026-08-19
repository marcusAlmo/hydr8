"""Presentation layer for the Settings page.

Transforms raw SystemConfig values, Company instances, and User
instances into template-ready dicts. All label maps, display
formatting, and tab/card shaping live here — selectors stay focused
on reading config values from the database.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.utils import timezone

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

# Mapping between raw lockscreen minutes and the display select options.
# "Never" is represented as 0 minutes internally.
_LOCKSCREEN_DISPLAY_TO_RAW = {
    '5 min': '5',
    '15 min': '15',
    '30 min': '30',
    'Never': '0',
}
_LOCKSCREEN_RAW_TO_DISPLAY = {v: k for k, v in _LOCKSCREEN_DISPLAY_TO_RAW.items()}

# Tab definitions are static — identical to the original mock.
_SETTINGS_TABS = [
    {'id': 'system-config', 'label': 'System Config', 'icon': 'tune', 'active': True},
    {'id': 'company', 'label': 'Company', 'icon': 'business', 'active': False},
    {'id': 'profile', 'label': 'My Profile', 'icon': 'account_circle', 'active': False},
]


def format_tithe_rate_display(raw: str) -> str:
    """Convert the stored decimal fraction (0.10) to a percentage (10.00)."""
    try:
        return f"{(Decimal(raw) * 100).quantize(Decimal('0.01'))}"
    except (InvalidOperation, ValueError):
        return '10.00'


def format_currency_display(raw: str) -> str:
    """Convert a raw numeric string (3000.00) to a grouped display (3,000.00)."""
    try:
        dec = Decimal(raw).quantize(Decimal('0.01'))
        return f"{dec:,.2f}"
    except (InvalidOperation, ValueError):
        return raw


def format_lockscreen_display(raw: str) -> str:
    """Convert raw minutes (5) to the select-option label (5 min)."""
    return _LOCKSCREEN_RAW_TO_DISPLAY.get(raw, f"{raw} min")


def format_system_config_row(key: str, raw_value: str) -> dict[str, Any]:
    """Build a single System Config tab row from a raw value + metadata."""
    meta = SYSTEM_CONFIG_METADATA[key]
    if key == 'tithe_rate':
        display_value = format_tithe_rate_display(raw_value)
    elif key == 'approved_credit_limit':
        display_value = format_currency_display(raw_value)
    elif key == 'lockscreen_timeout_minutes':
        display_value = format_lockscreen_display(raw_value)
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
        'raw_value': raw_value,
    }


def build_system_config(config_values: dict[str, str]) -> list[dict[str, Any]]:
    """Build the list of System Config rows in display order.

    ``config_values`` is a dict of {key: raw_value} for all config keys.
    """
    rows = []
    for key in (
        'lockscreen_timeout_minutes',
        'tithe_rate',
        'approved_credit_limit',
        'approved_container_limit',
        'overdue_threshold_days',
    ):
        raw = config_values.get(key, '')
        rows.append(format_system_config_row(key, raw))
    return rows


def build_company_context(user) -> dict[str, str]:
    """Build the Company tab context from the user's tenant."""
    company = getattr(user, 'company', None)
    if company is None:
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


def build_profile_context(user) -> dict[str, str]:
    """Build the My Profile tab context from the logged-in user."""
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


def build_settings_context(
    *,
    user,
    config_values: dict[str, str],
) -> dict[str, Any]:
    """Compose the full Settings page context dict.

    ``config_values`` is a dict of {key: raw_value} for all SystemConfig
    keys, fetched by the selector layer.
    """
    company_id = getattr(getattr(user, 'company', None), 'id', None)

    if is_staff_role(user):
        tabs = [t for t in _SETTINGS_TABS if t['id'] == 'profile']
    else:
        tabs = _SETTINGS_TABS

    return {
        'today_date': timezone.localtime().strftime('%A, %b %d, %Y'),
        'tabs': tabs,
        'system_config': build_system_config(config_values),
        'company': build_company_context(user),
        'profile': build_profile_context(user),
    }
