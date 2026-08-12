"""Read-side selectors for the audit log page.

All views MUST call these functions instead of querying LogEntry directly.
This keeps N+1 prevention (select_related) and tenant scoping in one place.
"""
import json
import logging

from django.core.paginator import Paginator
from django.db.models import Count, Q

from auditlog.models import LogEntry

logger = logging.getLogger(__name__)

PER_PAGE = 50

_ACTION_LABELS = {0: "CREATE", 1: "UPDATE", 2: "DELETE", 3: "ACCESS"}

_ACTION_BADGE_CLASSES = {
    0: "bg-tertiary-container/20 text-tertiary border-tertiary/30",
    1: "bg-primary/10 text-primary border-primary/30",
    2: "bg-error/10 text-error border-error/30",
    3: "bg-[#D97706]/15 text-[#D97706] border-[#D97706]/30",
}


def _tenant_filter(qs, user):
    """Scope to the user's company. Platform superusers (company_id is None) see all."""
    if user.company_id is None:
        return qs
    return qs.filter(actor__company_id=user.company_id)


def _enrich_entry(entry):
    """Adds display-only attributes to a LogEntry instance for template rendering."""
    entry.action_label = _ACTION_LABELS.get(entry.action, "ACCESS")
    entry.badge_class = _ACTION_BADGE_CLASSES.get(
        entry.action, "bg-surface-container text-on-surface-variant"
    )
    entry.actor_display = entry.actor.full_name if entry.actor else "System"
    entry.actor_email = entry.actor_email or (entry.actor.email if entry.actor else None)
    if entry.content_type:
        model_class = entry.content_type.model_class()
        entry.content_type_str = (
            f"{entry.content_type.app_label}.{model_class.__name__}"
            if model_class
            else f"{entry.content_type.app_label}.{entry.content_type.model}"
        )
    else:
        entry.content_type_str = "—"
    changes = entry.changes or {}
    entry.changes_summary = f"{len(changes)} field(s) changed" if changes else "—"


def list_log_entries(*, user, page: int = 1, per_page: int = PER_PAGE, query: str = "") -> dict:
    """Returns a paginated, enriched, tenant-scoped view of the audit log.

    When ``query`` is non-empty, filters by object_repr, cid, remote_addr,
    or actor name/username using ``__icontains``.

    Returns a dict with:
        page_obj:      Django Page object (object_list entries are enriched)
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

    for entry in page_obj.object_list:
        _enrich_entry(entry)

    return {
        "page_obj": page_obj,
        "paginator": paginator,
        "total": total,
        "action_counts": action_counts,
        "active_actors": active_actors,
    }


def get_log_entry(*, entry_id: int, user):
    """Returns a single enriched LogEntry, or None if not found / out of tenant scope."""
    qs = LogEntry.objects.select_related("actor", "content_type")
    qs = _tenant_filter(qs, user)
    try:
        entry = qs.get(pk=entry_id)
    except LogEntry.DoesNotExist:
        return None
    _enrich_entry(entry)
    return entry


def build_logs_json(entries) -> str:
    """Serializes enriched LogEntry entries to JSON for Alpine.js client-side filtering."""
    return json.dumps([
        {
            "id": e.pk,
            "timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "action": e.action,
            "action_label": e.action_label,
            "badge_class": e.badge_class,
            "actor_display": e.actor_display,
            "actor_email": e.actor_email,
            "is_system": e.actor_display in ("System", "system-scheduler"),
            "initials": e.actor_display[:2].upper(),
            "content_type": e.content_type_str,
            "object_repr": e.object_repr,
            "changes_summary": e.changes_summary,
            "remote_addr": e.remote_addr,
            "cid": e.cid,
        }
        for e in entries
    ])
