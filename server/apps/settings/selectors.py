"""Read-side selectors for the Settings page.

The Settings page has four tabs (System Config, Company, My Profile, AI
Model).  Each tab consumes a different slice of data:

  * System Config — key/value rows from ``core.SystemConfig`` enriched
    with UI metadata (label, description, widget type, options).
  * Company       — the tenant's ``settings.Company`` row.
  * My Profile    — the logged-in user's ``User`` record.
  * AI Model      — a handful of ``SystemConfig`` AI keys, enriched with
    display metadata (size, latency, status badge class).

These selectors return plain dicts shaped to match the existing mock
context so the templates need minimal changes.  No business logic lives
here — only reads + formatting.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.core.models import SystemConfig


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
}

# Raw default values used when a key is missing from the DB (defensive —
# the seed migration should have created them, but we never want the
# Settings page to crash because a row is absent).
SYSTEM_CONFIG_DEFAULTS: dict[str, str] = {
    'lockscreen_timeout_minutes': '5',
    'tithe_rate': '0.10',
    'approved_credit_limit': '3000.00',
    'approved_container_limit': '20',
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
# AI Model tab — display metadata.
#
# The AI tab is read-only ("Coming Soon" per the template).  These values
# are either derived from SystemConfig or are static display strings.
# ---------------------------------------------------------------------------
AI_MODEL_DEFAULTS: dict[str, str] = {
    'ai_model_id': 'gemma-2-2b-it-q4f16_1-MLC',
    'ai_model_version': '2b-q4f16',
    'ai_download_status': 'not_started',
    'ai_download_percent': '0',
}

# Static display metadata for the Gemma 2B model card.  model_size and
# latency are not persisted server-side (latency is client-measured;
# size is a property of the model ID).
AI_MODEL_DISPLAY = {
    'name': 'Gemma 2B',
    'description': 'Optimized for logistics forecasting and routing.',
    'model_size': '1.2 GB',
    'latency': '~140ms',
}

# Maps the raw ai_download_status to a display label + Tailwind badge class.
AI_STATUS_STYLING: dict[str, dict[str, str]] = {
    'not_started': {
        'label': 'Not Started',
        'status_class': 'bg-surface-container-high text-on-surface-variant border-outline-variant/30',
    },
    'downloading': {
        'label': 'Downloading',
        'status_class': 'bg-secondary-container text-on-secondary border-secondary/30',
    },
    'ready': {
        'label': 'Ready',
        'status_class': 'bg-tertiary-container/20 text-tertiary border-tertiary/30',
    },
}


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
    return SYSTEM_CONFIG_DEFAULTS.get(key, AI_MODEL_DEFAULTS.get(key, ''))


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


def _build_ai_model_context(company_id: int | None) -> dict[str, Any]:
    """Builds the AI Model tab context (read-only display)."""
    status_raw = _get_config_value('ai_download_status', company_id)
    percent_raw = _get_config_value('ai_download_percent', company_id)
    styling = AI_STATUS_STYLING.get(status_raw, AI_STATUS_STYLING['not_started'])

    try:
        percent = int(percent_raw)
    except (TypeError, ValueError):
        percent = 0

    return {
        'name': AI_MODEL_DISPLAY['name'],
        'description': AI_MODEL_DISPLAY['description'],
        'status': styling['label'],
        'status_class': styling['status_class'],
        'model_size': AI_MODEL_DISPLAY['model_size'],
        'latency': AI_MODEL_DISPLAY['latency'],
        'last_update': '—',  # not persisted; placeholder
        'download_progress': percent,
        'download_complete': percent >= 100,
    }


# ---------------------------------------------------------------------------
# Public selector — returns the full Settings page context.
# ---------------------------------------------------------------------------

# Tab definitions are static — identical to the original mock.
_SETTINGS_TABS = [
    {'id': 'system-config', 'label': 'System Config', 'icon': 'tune', 'active': True},
    {'id': 'company', 'label': 'Company', 'icon': 'business', 'active': False},
    {'id': 'profile', 'label': 'My Profile', 'icon': 'account_circle', 'active': False},
    {'id': 'ai-model', 'label': 'AI Model', 'icon': 'smart_toy', 'active': False},
]


def get_settings_context(user) -> dict[str, Any]:
    """Returns the full context dict consumed by ``settings/settings.html``.

    Replaces the former ``_mock_settings_data`` helper.  The shape is
    identical so the templates need no structural changes — only the
    values are now sourced from the database.
    """
    company_id = getattr(getattr(user, 'company', None), 'id', None)

    return {
        'today_date': datetime.now().strftime('%A, %b %d, %Y'),
        'tabs': _SETTINGS_TABS,
        'system_config': _build_system_config(company_id),
        'company': _build_company_context(user),
        'profile': _build_profile_context(user),
        'ai_model': _build_ai_model_context(company_id),
    }
