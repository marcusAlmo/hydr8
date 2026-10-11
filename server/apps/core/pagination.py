"""Core pagination constants and helpers for Hydr8."""
from typing import Any

DEFAULT_PER_PAGE: int = 10
PER_PAGE_CHOICES: tuple[int, ...] = (10, 15, 20, 25)


def parse_per_page(value: Any, default: int = DEFAULT_PER_PAGE) -> int:
    """Safely parse and validate a per_page / page_size query parameter.

    Only values in PER_PAGE_CHOICES (10, 15, 20, 25) are accepted;
    any missing, invalid, or out-of-range value falls back to default.
    """
    if value is None:
        return default
    try:
        val = int(value)
        if val in PER_PAGE_CHOICES:
            return val
    except (TypeError, ValueError):
        pass
    return default
