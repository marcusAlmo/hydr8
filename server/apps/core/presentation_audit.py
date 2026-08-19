"""Presentation layer for the audit log page.

Transforms LogEntry model instances into template-ready display
attributes and JSON-serializable dicts. All label maps, CSS class
maps, display-string formatting, and context dict shaping live here
— selectors stay focused on tenant-scoped queries and pagination.
"""
import json

from django.utils import timezone

from auditlog.models import LogEntry

_ACTION_LABELS = {0: "CREATE", 1: "UPDATE", 2: "DELETE", 3: "ACCESS"}

_ACTION_BADGE_CLASSES = {
    0: "bg-tertiary-container/20 text-tertiary border-tertiary/30",
    1: "bg-primary/10 text-primary border-primary/30",
    2: "bg-error/10 text-error border-error/30",
    3: "bg-[#D97706]/15 text-[#D97706] border-[#D97706]/30",
}


def enrich_entry(entry: LogEntry) -> None:
    """Add display-only attributes to a LogEntry for template rendering.

    Mutates the entry in place, adding:
    - ``action_label``: human-readable action name
    - ``badge_class``: Tailwind classes for the action badge
    - ``actor_display``: full name or "System"
    - ``actor_email``: resolved email
    - ``content_type_str``: "app.Model" string
    - ``changes_summary``: "N field(s) changed" or "—"
    """
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


def build_logs_json(entries) -> str:
    """Serialize enriched LogEntry entries to JSON for Alpine.js filtering."""
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


def build_action_filters(total: int, action_counts: dict) -> list[dict]:
    """Shape the action filter chips for the audit log sidebar."""
    return [
        {"value": "", "label": "All Actions", "count": total, "active": True},
        {"value": "0", "label": "Create", "count": action_counts.get(0, 0), "active": False},
        {"value": "1", "label": "Update", "count": action_counts.get(1, 0), "active": False},
        {"value": "2", "label": "Delete", "count": action_counts.get(2, 0), "active": False},
        {"value": "3", "label": "Access", "count": action_counts.get(3, 0), "active": False},
    ]


def build_stats(total: int, action_counts: dict, active_actors: int) -> list[dict]:
    """Shape the summary stat cards for the audit log page."""
    mutations = sum(action_counts.get(a, 0) for a in (0, 1, 2))
    access_events = action_counts.get(3, 0)
    return [
        {
            "label": "Total Entries",
            "value": str(total),
            "raw_value": total,
            "value_prefix": "",
            "value_decimals": 0,
            "icon": "history",
            "accent": "text-primary",
        },
        {
            "label": "Mutations",
            "value": str(mutations),
            "raw_value": mutations,
            "value_prefix": "",
            "value_decimals": 0,
            "icon": "edit_note",
            "accent": "text-tertiary",
        },
        {
            "label": "Access Events",
            "value": str(access_events),
            "raw_value": access_events,
            "value_prefix": "",
            "value_decimals": 0,
            "icon": "login",
            "accent": "text-[#D97706]",
        },
        {
            "label": "Active Actors",
            "value": str(active_actors),
            "raw_value": active_actors,
            "value_prefix": "",
            "value_decimals": 0,
            "icon": "group",
            "accent": "text-secondary",
        },
    ]


def build_pagination(page_obj, total: int) -> dict:
    """Shape the pagination context dict from a Django Page object."""
    return {
        "showing_from": page_obj.start_index() if page_obj.object_list else 0,
        "showing_to": page_obj.end_index() if page_obj.object_list else 0,
        "total_display": str(total),
        "current_page": page_obj.number,
        "total_pages": page_obj.paginator.num_pages,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
        "previous_page_number": page_obj.previous_page_number() if page_obj.has_previous() else None,
        "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None,
    }


def build_list_context(*, page_obj, total: int, action_counts: dict, active_actors: int,
                       query: str = "", for_htmx: bool = False) -> dict:
    """Build the full template context for the audit log list page.

    Enriches each LogEntry in the page with display attributes, then
    composes the action filters, stats, pagination, and JSON seeds.
    """
    for entry in page_obj.object_list:
        enrich_entry(entry)

    action_filters = build_action_filters(total, action_counts)
    stats = build_stats(total, action_counts, active_actors)
    pagination = build_pagination(page_obj, total)

    if for_htmx:
        logs_json = "[]"
        action_counts_json = "{}"
    else:
        logs_json = build_logs_json(page_obj.object_list)
        action_counts_json = json.dumps({
            "total": total,
            "0": action_counts.get(0, 0),
            "1": action_counts.get(1, 0),
            "2": action_counts.get(2, 0),
            "3": action_counts.get(3, 0),
        })

    return {
        "today_date": timezone.localtime().strftime("%A, %b %d, %Y"),
        "logs": page_obj.object_list,
        "total": total,
        "action_filters": action_filters,
        "stats": stats,
        "pagination": pagination,
        "logs_json": logs_json,
        "action_counts_json": action_counts_json,
        "page_obj": page_obj,
        "search_query": query,
    }


def build_changes_list(entry: LogEntry) -> list[dict]:
    """Format a LogEntry's changes dict into a diff-table-ready list."""
    changes_list = []
    changes = entry.changes or {}
    for field, values in changes.items():
        old_val = values[0] if len(values) > 0 and values[0] is not None else None
        new_val = values[1] if len(values) > 1 and values[1] is not None else None
        changes_list.append({
            "field": field,
            "old": old_val if old_val is not None else "—",
            "new": new_val if new_val is not None else "—",
            "is_new_field": old_val is None,
            "is_deleted_field": new_val is None,
        })
    return changes_list


def enrich_detail_entry(entry: LogEntry) -> None:
    """Enrich a LogEntry for the detail modal (adds changes_list + pretty JSON)."""
    enrich_entry(entry)
    entry.changes_list = build_changes_list(entry)
    if entry.serialized_data:
        entry.serialized_data_pretty = json.dumps(entry.serialized_data, indent=2)
    if entry.additional_data:
        entry.additional_data_pretty = json.dumps(entry.additional_data, indent=2)
