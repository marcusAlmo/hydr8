"""Read-side selectors for the audit log page.

All views MUST call these functions instead of querying LogEntry directly.
This keeps N+1 prevention (select_related) and tenant scoping in one place.
"""
import json
import logging

from datetime import date, datetime, time, timedelta

from auditlog.models import LogEntry
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone

from apps.core.pagination import DEFAULT_PER_PAGE

logger = logging.getLogger(__name__)

PER_PAGE = DEFAULT_PER_PAGE

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
    return qs.filter(
        Q(actor__company_id=user.company_id)
        | Q(additional_data__company_id=user.company_id)
    )


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
            model_class._meta.verbose_name.title()
            if model_class
            else entry.content_type.name.title()
        )
    else:
        entry.content_type_str = "—"
    changes = entry.changes or {}
    entry.changes_summary = f"{len(changes)} field(s) changed" if changes else "—"


def list_log_entries(
    *,
    user,
    page: int = 1,
    per_page: int = PER_PAGE,
    query: str = "",
    action: str = "",
    date_range: str = "all",
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Returns a paginated, enriched, tenant-scoped view of the audit log.

    When ``query`` is non-empty, filters by object_repr, cid, remote_addr,
    or actor name/username using ``__ilike``.
    When ``action`` is provided (0, 1, 2, 3), narrows to that action.
    When ``date_range`` or ``start_date``/``end_date`` is provided, narrows by timestamp.

    Returns a dict with:
        page_obj:          Django Page object (object_list entries are enriched)
        paginator:         Paginator instance
        total:             filtered total count matching action, date, and query
        date_scoped_total: total count matching date and query (before action filter)
        action_counts:     {0: int, 1: int, 2: int, 3: int} matching date and query
        active_actors:     count of distinct non-null actors matching date and query
        active_action:     string representation of current action filter
        date_range:        current date range key
        start_date:        start date if custom range
        end_date:          end date if custom range
    """
    qs = (
        LogEntry.objects
        .select_related("actor", "content_type")
        .order_by("-timestamp")
    )
    qs = _tenant_filter(qs, user)

    # Apply date range filter
    now = timezone.now()
    today = timezone.localdate()
    if date_range == "today":
        today_start = timezone.make_aware(datetime.combine(today, time.min))
        qs = qs.filter(timestamp__gte=today_start)
    elif date_range == "7d":
        qs = qs.filter(timestamp__gte=now - timedelta(days=7))
    elif date_range == "30d":
        qs = qs.filter(timestamp__gte=now - timedelta(days=30))
    elif date_range == "custom" and start_date and end_date:
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
        end_dt = timezone.make_aware(datetime.combine(end_date, time.max))
        qs = qs.filter(timestamp__range=(start_dt, end_dt))

    # Apply search filter
    query = (query or "").strip()
    if query:
        qs = qs.filter(
            Q(object_repr__ilike=query)
            | Q(cid__ilike=query)
            | Q(remote_addr__ilike=query)
            | Q(actor__username__ilike=query)
            | Q(actor__first_name__ilike=query)
            | Q(actor__last_name__ilike=query)
        )

    # Action counts scoped to current date range & search query (before action filter)
    date_scoped_total = qs.count()
    action_counts_raw = qs.order_by().values("action").annotate(count=Count("id"))
    action_counts = {item["action"]: item["count"] for item in action_counts_raw}
    active_actors = qs.order_by().exclude(actor=None).values("actor").distinct().count()

    # Apply action filter
    action = (action or "").strip()
    if action in ("0", "1", "2", "3"):
        qs = qs.filter(action=int(action))

    total = qs.count()
    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page)

    for entry in page_obj.object_list:
        _enrich_entry(entry)

    return {
        "page_obj": page_obj,
        "paginator": paginator,
        "total": total,
        "date_scoped_total": date_scoped_total,
        "action_counts": action_counts,
        "active_actors": active_actors,
        "active_action": action,
        "date_range": date_range,
        "start_date": start_date,
        "end_date": end_date,
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


def build_logs_data(entries) -> list[dict]:
    """Returns serializable dict projections of enriched LogEntry entries."""
    return [
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
    ]


def build_logs_json(entries) -> str:
    """Serializes enriched LogEntry entries to JSON for backwards compatibility."""
    return json.dumps(build_logs_data(entries))

