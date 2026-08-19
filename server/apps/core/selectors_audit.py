"""Read-side selectors for the audit log page.

Selectors return raw LogEntry instances and aggregate counts. All
display attribute enrichment (labels, CSS classes, content-type
strings) lives in ``presentation_audit.py``. Views call selectors for
data, then call presentation functions to prepare entries for
rendering.
"""
import logging

from django.core.paginator import Paginator
from django.db.models import Count, Q

from auditlog.models import LogEntry

logger = logging.getLogger(__name__)

PER_PAGE = 50


def _tenant_filter(qs, user):
    """Scope to the user's company. Platform superusers (company_id is None) see all."""
    if user.company_id is None:
        return qs
    return qs.filter(actor__company_id=user.company_id)


def list_log_entries(*, user, page: int = 1, per_page: int = PER_PAGE, query: str = "") -> dict:
    """Return a paginated, tenant-scoped view of the audit log.

    When ``query`` is non-empty, filters by object_repr, cid, remote_addr,
    or actor name/username using ``__icontains``.

    Returns a dict with:
        page_obj:      Django Page object (raw LogEntry instances)
        paginator:     Paginator instance
        total:         total entry count (full queryset)
        action_counts: {0: int, 1: int, 2: int, 3: int} (full queryset)
        active_actors: count of distinct non-null actors (full queryset)
    """
    qs = (
        LogEntry.objects
        .select_related("actor", "content_type")
        .order_by("-timestamp")
    )
    qs = _tenant_filter(qs, user)

    # Apply search filter
    query = (query or "").strip()
    if query:
        qs = qs.filter(
            Q(object_repr__icontains=query)
            | Q(cid__icontains=query)
            | Q(remote_addr__icontains=query)
            | Q(actor__username__icontains=query)
            | Q(actor__first_name__icontains=query)
            | Q(actor__last_name__icontains=query)
        )

    # Aggregate counts from the full queryset (single query via values+annotate)
    total = qs.count()
    action_counts_raw = qs.values("action").annotate(count=Count("action"))
    action_counts = {item["action"]: item["count"] for item in action_counts_raw}
    active_actors = qs.exclude(actor=None).values("actor").distinct().count()

    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page)

    return {
        "page_obj": page_obj,
        "paginator": paginator,
        "total": total,
        "action_counts": action_counts,
        "active_actors": active_actors,
    }


def get_log_entry(*, entry_id: int, user):
    """Return a single LogEntry, or None if not found / out of tenant scope."""
    qs = LogEntry.objects.select_related("actor", "content_type")
    qs = _tenant_filter(qs, user)
    try:
        return qs.get(pk=entry_id)
    except LogEntry.DoesNotExist:
        return None
