import json
import logging
from datetime import date, datetime

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.audit.selectors import (
    build_logs_data,
    get_log_entry,
    list_log_entries,
)
from apps.core.pagination import (
    DEFAULT_PER_PAGE,
    PER_PAGE_CHOICES,
    get_elided_page_numbers,
    parse_per_page,
)
from apps.users.permissions import is_admin

logger = logging.getLogger(__name__)


def _build_list_context(
    *,
    user,
    page: int,
    query: str = "",
    action: str = "",
    date_range: str = "7d",
    start_date: date | None = None,
    end_date: date | None = None,
    for_htmx: bool = False,
    per_page: int = DEFAULT_PER_PAGE,
) -> dict:
    """Builds the template context for the audit log list page from real data."""
    data = list_log_entries(
        user=user,
        page=page,
        per_page=per_page,
        query=query,
        action=action,
        date_range=date_range,
        start_date=start_date,
        end_date=end_date,
    )
    page_obj = data["page_obj"]
    action_counts = data["action_counts"]
    total = data["total"]

    action_filters = [
        {"value": "", "label": "All Actions", "count": data["date_scoped_total"], "active": action == ""},
        {"value": "0", "label": "Create", "count": action_counts.get(0, 0), "active": action == "0"},
        {"value": "1", "label": "Update", "count": action_counts.get(1, 0), "active": action == "1"},
        {"value": "2", "label": "Delete", "count": action_counts.get(2, 0), "active": action == "2"},
        {"value": "3", "label": "Access", "count": action_counts.get(3, 0), "active": action == "3"},
    ]

    mutations = sum(action_counts.get(a, 0) for a in (0, 1, 2))
    access_events = action_counts.get(3, 0)
    date_scoped_total = data["date_scoped_total"]
    stats = [
        {
            "label": "Total Entries",
            "value": str(date_scoped_total),
            "raw_value": date_scoped_total,
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
            "value": str(data["active_actors"]),
            "raw_value": data["active_actors"],
            "value_prefix": "",
            "value_decimals": 0,
            "icon": "group",
            "accent": "text-secondary",
        },
    ]

    pagination = {
        "showing_from": page_obj.start_index() if total else 0,
        "showing_to": page_obj.end_index() if total else 0,
        "total": total,
        "total_display": f"{total:,}",
        "current_page": page_obj.number,
        "total_pages": page_obj.paginator.num_pages if total else 0,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
        "previous_page_number": page_obj.previous_page_number() if page_obj.has_previous() else None,
        "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None,
        "per_page": page_obj.paginator.per_page,
        "per_page_choices": list(PER_PAGE_CHOICES),
        "page_numbers": get_elided_page_numbers(page_obj.number, page_obj.paginator.num_pages) if total else [],
    }

    if for_htmx:
        logs_json = "[]"
        action_counts_json = "{}"
        logs_data = []
        action_counts_data = {}
    else:
        # JSON-serializable projection for Alpine.js client-side filtering.
        # Only the current page's entries are included -- filters apply within the page.
        logs_data = build_logs_data(page_obj.object_list)
        logs_json = json.dumps(logs_data)

        # Action counts for the Alpine filter chips (full dataset counts)
        action_counts_data = {
            "total": data["date_scoped_total"],
            "0": action_counts.get(0, 0),
            "1": action_counts.get(1, 0),
            "2": action_counts.get(2, 0),
            "3": action_counts.get(3, 0),
        }
        action_counts_json = json.dumps(action_counts_data)

    return {
        "today_date": timezone.localtime().strftime("%A, %b %d, %Y"),
        "logs": page_obj.object_list,
        "logs_data": logs_data,
        "action_counts_data": action_counts_data,
        "total": total,
        "date_scoped_total": data["date_scoped_total"],
        "action_filters": action_filters,
        "stats": stats,
        "pagination": pagination,
        "logs_json": logs_json,
        "action_counts_json": action_counts_json,
        "page_obj": page_obj,
        "search_query": query,
        "active_action": action,
        "date_range": date_range,
        "custom_from": start_date.strftime("%Y-%m-%d") if start_date else "",
        "custom_to": end_date.strftime("%Y-%m-%d") if end_date else "",
        "for_htmx": for_htmx,
    }


def _forbidden_response(request) -> HttpResponse:
    """Returns a 403 response; HTMX requests receive a toast trigger."""
    if request.headers.get("HX-Request") == "true":
        response = HttpResponse(status=403)
        response["HX-Trigger"] = json.dumps({"showToast": "You do not have permission to view the audit log."})
        return response
    return HttpResponse("Forbidden", status=403)


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def audit_log_view(request):
    """Renders the Audit Log page from real django-auditlog LogEntry records.

    Restricted to Admin (and platform superusers). Staff users do not access
    the Audit Log.

    For HTMX requests (search/pagination), returns just the table partial.
    For full page loads, renders the complete audit_log.html.
    """
    if not is_admin(request.user):
        return _forbidden_response(request)
    try:
        page = int(request.GET.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    query = request.GET.get("q", "")
    action = request.GET.get("action", "")
    date_range = (request.GET.get("range") or "7d").strip().lower()
    from_str = request.GET.get("from")
    to_str = request.GET.get("to")
    start_date = None
    end_date = None
    if from_str and to_str:
        try:
            start_date = datetime.strptime(from_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(to_str, "%Y-%m-%d").date()
            if start_date > end_date:
                start_date, end_date = end_date, start_date
            date_range = "custom"
        except ValueError:
            start_date = None
            end_date = None
    elif date_range not in ("today", "7d", "30d", "all"):
        date_range = "7d"

    per_page = parse_per_page(request.GET.get("per_page"))
    for_htmx = getattr(request, "htmx", False) and not getattr(request.htmx, "boosted", False)
    context = _build_list_context(
        user=request.user,
        page=page,
        query=query,
        action=action,
        date_range=date_range,
        start_date=start_date,
        end_date=end_date,
        for_htmx=for_htmx,
        per_page=per_page,
    )

    # Internal HTMX requests (search/pagination) get just the table partial;
    # full page and boosted navigation requests get the complete page.
    if for_htmx:
        return render(request, "audit/partials/audit_log_table.html", context)
    return render(request, "audit/audit_log.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def audit_log_detail_view(request, entry_id: int):
    """HTMX endpoint -- returns the detail modal partial for a single LogEntry.

    Restricted to Admin (and platform superusers).
    """
    if not is_admin(request.user):
        return _forbidden_response(request)
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
