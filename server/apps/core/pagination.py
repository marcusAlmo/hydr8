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


def get_elided_page_numbers(current_page: int, total_pages: int) -> list[int | str]:
    """Generates an elided page range with at most 5 clickable page numbers.

    Always includes page 1 (first) and total_pages (last) when total_pages > 5,
    with ellipses ('…') indicating skipped ranges, e.g.:
        Page 1:  [1, 2, 3, 4, '…', 72]
        Page 4:  [1, '…', 3, 4, 5, '…', 72]
        Page 72: [1, '…', 69, 70, 71, 72]
    """
    if total_pages <= 0:
        return []
    if total_pages <= 5:
        return list(range(1, total_pages + 1))
    current = max(1, min(current_page, total_pages))
    if current <= 3:
        return [1, 2, 3, 4, "…", total_pages]
    if current >= total_pages - 2:
        return [1, "…", total_pages - 3, total_pages - 2, total_pages - 1, total_pages]
    return [1, "…", current - 1, current, current + 1, "…", total_pages]

