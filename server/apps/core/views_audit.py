import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.core.selectors_audit import get_log_entry, list_log_entries
from apps.core.presentation_audit import build_list_context, enrich_detail_entry
from apps.users.permissions import is_admin

logger = logging.getLogger(__name__)


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
    for_htmx = request.headers.get("HX-Request") == "true"

    data = list_log_entries(user=request.user, page=page, query=query)
    context = build_list_context(
        page_obj=data["page_obj"],
        total=data["total"],
        action_counts=data["action_counts"],
        active_actors=data["active_actors"],
        query=query,
        for_htmx=for_htmx,
    )

    # HTMX requests get just the table partial; full loads get the page
    if request.headers.get("HX-Request") == "true":
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

    enrich_detail_entry(entry)
    return render(request, "audit/partials/detail_modal.html", {"entry": entry})
