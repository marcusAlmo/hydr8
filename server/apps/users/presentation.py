"""Presentation helpers for user-derived UI elements.

These functions derive *purely presentational* attributes (initials, avatar
colour palette) from a ``User`` instance.  They contain no business logic
and no PII beyond what is already displayed in the UI — they are safe to
call from selectors and templates.

The avatar palette is a fixed rotation of Material Design 3 container
tokens used across the app (products commission matrix, employees table,
audit log).  Selection is deterministic based on a hash of the user's pk
so the same user always gets the same colour without persisting it.
"""
from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.users.models import User


# --- Avatar palette -------------------------------------------------------
# Ordered to maximise visual contrast between adjacent rows in a table.
# Each entry is a (bg_class, text_class) pair using the project's semantic
# M3 container tokens (see tailwind.config / base.html).
_AVATAR_PALETTE: tuple[tuple[str, str], ...] = (
    ("bg-primary-fixed",        "text-on-primary-fixed"),
    ("bg-secondary-fixed",      "text-on-secondary-fixed"),
    ("bg-tertiary-fixed",       "text-on-tertiary-fixed"),
    ("bg-primary-container",    "text-on-primary-container"),
    ("bg-secondary-container",  "text-on-secondary-container"),
    ("bg-tertiary-container",   "text-on-tertiary-container"),
)


def initials(user: User) -> str:
    """Returns a 2-character initials string for avatar display.

    Preference order:
      1. First letters of first_name + last_name (e.g. "Juan Cruz" → "JC")
      2. First two letters of username uppercased (e.g. "juan.d" → "JU")
      3. Fallback "U" for empty usernames (defensive).
    """
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first and last:
        return f"{first[0]}{last[0]}".upper()
    if first:
        return first[:2].upper()
    username = (user.username or "").strip()
    if username:
        return username[:2].upper()
    return "U"


def avatar_classes(user: User) -> tuple[str, str]:
    """Returns a deterministic ``(bg_class, text_class)`` pair for the user.

    The pair is selected by hashing the user's pk and indexing into the
    fixed palette — the same user always gets the same colour, without
    persisting a colour preference.
    """
    pk_str = str(getattr(user, "pk", "") or "")
    digest = hashlib.md5(pk_str.encode("utf-8")).digest()
    idx = digest[0] % len(_AVATAR_PALETTE)
    return _AVATAR_PALETTE[idx]


def driver_code(user: User) -> str:
    """Returns a human-friendly driver code derived from the user's pk.

    Format: ``DRV-<pk zero-padded to 3 digits>`` (e.g. pk=1 → "DRV-001",
    pk=42 → "DRV-042").  Pks >= 1000 are printed without padding.
    """
    pk = getattr(user, "pk", None)
    if pk is None:
        return "DRV-000"
    if isinstance(pk, int) or (isinstance(pk, str) and pk.isdigit()):
        pk_int = int(pk)
        return f"DRV-{pk_int:03d}" if pk_int < 1000 else f"DRV-{pk_int}"
    # UUID pk — use first 4 hex chars for a short stable code.
    return f"DRV-{str(pk)[:4].upper()}"
