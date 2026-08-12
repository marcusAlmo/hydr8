import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.audit.selectors import (
    build_logs_json,
    get_log_entry,
    list_log_entries,
)
from apps.users.permissions import is_back_office

logger = logging.getLogger(__name__)


def _build_list_context(*, user, page: int, query: str = "") -> dict:
    """Builds the template context for the audit log list page from real data."""
    data = list_log_entries(user=user, page=page, query=query)
    page_obj = data["page_obj"]
    action_counts = data["action_counts"]

    action_filters = [
        {"value": "", "label": "All Actions", "count": data["total"], "active": True},
        {"value": "0", "label": "Create", "count": action_counts.get(0, 0), "active": False},
        {"value": "1", "label": "Update", "count": action_counts.get(1, 0), "active": False},
        {"value": "2", "label": "Delete", "count": action_counts.get(2, 0), "active": False},
        {"value": "3", "label": "Access", "count": action_counts.get(3, 0), "active": False},
    ]

    mutations = sum(action_counts.get(a, 0) for a in (0, 1, 2))
    access_events = action_counts.get(3, 0)
    stats = [
        {
            "label": "Total Entries",
            "value": str(data["total"]),
            "icon": "history",
            "accent": "text-primary",
        },
        {
            "label": "Mutations",
            "value": str(mutations),
            "icon": "edit_note",
            "accent": "text-tertiary",
        },
        {
            "label": "Access Events",
            "value": str(access_events),
            "icon": "login",
            "accent": "text-[#D97706]",
        },
        {
            "label": "Active Actors",
            "value": str(data["active_actors"]),
            "icon": "group",
            "accent": "text-secondary",
        },
    ]

    pagination = {
        "showing_from": page_obj.start_index() if page_obj.object_list else 0,
        "showing_to": page_obj.end_index() if page_obj.object_list else 0,
        "total_display": str(data["total"]),
        "current_page": page_obj.number,
        "total_pages": page_obj.paginator.num_pages,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
        "previous_page_number": page_obj.previous_page_number() if page_obj.has_previous() else None,
        "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None,
    }

    # JSON-serializable projection for Alpine.js client-side filtering.
    # Only the current page's entries are included -- filters apply within the page.
    logs_json = build_logs_json(page_obj.object_list)

    # JSON of action counts for the Alpine filter chips (full dataset counts)
    action_counts_json = json.dumps({
        "total": data["total"],
        "0": action_counts.get(0, 0),
        "1": action_counts.get(1, 0),
        "2": action_counts.get(2, 0),
        "3": action_counts.get(3, 0),
    })

    return {
        "today_date": timezone.localtime().strftime("%A, %b %d, %Y"),
        "logs": page_obj.object_list,
        "total": data["total"],
        "action_filters": action_filters,
        "stats": stats,
        "pagination": pagination,
        "logs_json": logs_json,
        "action_counts_json": action_counts_json,
        "page_obj": page_obj,
        "search_query": query,
    }


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def audit_log_view(request):
    if not is_back_office(request.user):
        return HttpResponse("Forbidden", status=403)
    """Renders the Audit Log page from real django-auditlog LogEntry records.

    For HTMX requests (search/pagination), returns just the table partial.
    For full page loads, renders the complete audit_log.html.
    """
    try:
        page = int(request.GET.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    query = request.GET.get("q", "")
    context = _build_list_context(user=request.user, page=page, query=query)

    # HTMX requests get just the table partial; full loads get the page
    if request.headers.get("HX-Request") == "true":
        return render(request, "audit/partials/audit_log_table.html", context)
    return render(request, "audit/audit_log.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def audit_log_detail_view(request, entry_id: int):
    if not is_back_office(request.user):
        return HttpResponse("Forbidden", status=403)
    """HTMX endpoint -- returns the detail modal partial for a single LogEntry."""
    entry = get_log_entry(entry_id=entry_id, user=request.user)
    if entry is None:
        return HttpResponse("Audit log entry not found.", status=404)

    # Format changes for the diff table -- convert {field: [old, new]} to list
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
    entry.changes_list = changes_list

    # Pretty-print serialized data and additional_data for collapsible sections
    if entry.serialized_data:
        entry.serialized_data_pretty = json.dumps(entry.serialized_data, indent=2)
    if entry.additional_data:
        entry.additional_data_pretty = json.dumps(entry.additional_data, indent=2)

    return render(request, "audit/partials/detail_modal.html", {"entry": entry})
