from __future__ import annotations

from django import template

from apps.core.pagination import get_elided_page_numbers

register = template.Library()


@register.filter(name="elided_pages")
def elided_pages(page_obj) -> list[int | str]:
    """Returns elided page numbers with at most 5 clickable numbers for a Page object."""
    if not page_obj or not hasattr(page_obj, "paginator") or page_obj.paginator.count == 0:
        return []
    return get_elided_page_numbers(page_obj.number, page_obj.paginator.num_pages)
