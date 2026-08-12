import json
import logging
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.core.views import error_message, toast_for_exception

from .selectors import (
    get_add_remittance_context,
    get_recent_remittances,
    get_remittance_history_context,
    get_remittance_row,
    remittance_exists_for_date,
)
from .services import create_and_finalize_remittance, update_remittance_paid_status

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def add_remittance_view(request):
    """Renders the 'Add Remittance' workflow page with live product/rider data."""
    context = get_add_remittance_context(request.user)
    riders = context["riders"]
    products = context["products"]

    selected_rider_id = next(
        (r["id"] for r in riders if r.get("selected")),
        riders[0]["id"] if riders else None,
    )

    context["alpine_seed"] = json.dumps({
        "riders": riders,
        "products": products,
        "expenses": context["expenses"],
        "titheRate": context["tithe_rate"],
        "manualOffering": context["offering_amount"],
        "selectedRiderId": selected_rider_id,
        "remittanceDate": context["default_date"],
    }).replace("'", "&#39;")

    return render(request, "remittance/add_remittance.html", context)


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def create_remittance_view(request):
    """HTMX/JSON endpoint — creates and finalizes a remittance from the
    Alpine.js form payload.
    """
    try:
        body = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)

    remittance_date = date.today()
    remittance_date_str = body.get("remittanceDate")
    if remittance_date_str:
        try:
            remittance_date = date.fromisoformat(str(remittance_date_str))
        except (ValueError, TypeError):
            logger.info("[%s] invalid remittance date: %s", request.user.id, remittance_date_str)
            return JsonResponse({"ok": False, "error": "Invalid remittance date."}, status=400)
    if remittance_date > date.today():
        logger.info("[%s] future remittance date: %s", request.user.id, remittance_date)
        return JsonResponse({"ok": False, "error": "Remittance date cannot be in the future."}, status=400)

    try:
        create_and_finalize_remittance(
            performed_by=request.user,
            riders_data=body.get("riders", []) or [],
            expenses_data=body.get("expenses", []) or [],
            manual_offering=body.get("manualOffering", "0"),
            tithe_rate=body.get("titheRate", "0.10"),
            remittance_date=remittance_date,
        )
    except ValidationError as e:
        logger.info("[%s] create remittance validation error: %s", request.user.id, e)
        return JsonResponse({"ok": False, "error": error_message(e)}, status=400)
    except (KeyError, ValueError, TypeError) as e:
        logger.info("[%s] create remittance input error: %s", request.user.id, e)
        return JsonResponse({"ok": False, "error": f"Invalid input: {e}"}, status=400)

    return JsonResponse({"ok": True, "redirect_url": reverse("remittance:history")})


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def check_remittance_date_view(request):
    """JSON endpoint — returns whether a remittance already exists for a date."""
    date_str = request.GET.get("date")
    if not date_str:
        return JsonResponse({"ok": False, "error": "Date is required."}, status=400)

    try:
        target_date = date.fromisoformat(date_str)
    except (ValueError, TypeError):
        logger.info("[%s] invalid date in check request: %s", request.user.id, date_str)
        return JsonResponse({"ok": False, "error": "Invalid date format."}, status=400)

    exists = remittance_exists_for_date(request.user, target_date)
    return JsonResponse({"ok": True, "exists": exists})


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def remittance_history_view(request):
    """Renders the 'Remittance History' list page with live DB-backed data."""
    context = get_remittance_history_context(request.user)
    recent = get_recent_remittances(request.user)

    total = recent["total"]
    shown = len(recent["remittances"])
    per_page = 25
    total_pages = max(1, (total + per_page - 1) // per_page)

    context["remittances"] = recent["remittances"]
    context["pagination"] = {
        "showing": f"Showing {shown} of {total} records",
        "current_page": 1,
        "total_pages": total_pages,
    }

    context["trends_seed"] = json.dumps(context["trends"]).replace("'", "&#39;")
    return render(request, "remittance/remittance_history.html", context)


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def update_paid_status_view(request, remittance_id: int):
    """HTMX endpoint — updates ``tithes_paid`` / ``offering_paid`` flags on
    a single remittance and returns the refreshed row partial plus an
    out-of-band success toast.

    Checkboxes follow the standard HTML convention: present = ``on``,
    absent = unchecked. The endpoint swaps the row via ``outerHTML`` and
    appends a toast into ``#toast-container``.
    """
    tithes_paid = request.POST.get("tithes_paid") == "on"
    offering_paid = request.POST.get("offering_paid") == "on"

    try:
        update_remittance_paid_status(
            performed_by=request.user,
            remittance_id=remittance_id,
            tithes_paid=tithes_paid,
            offering_paid=offering_paid,
        )
    except ValidationError as exc:
        logger.info("[%s] update paid status error remittance_id=%s: %s",
                    request.user.id, remittance_id, error_message(exc))
        return toast_for_exception(request, exc)

    row = get_remittance_row(request.user, remittance_id)
    if row is None:
        return toast_for_exception(
            request, ValidationError("Remittance not found.")
        )

    row_html = render_to_string(
        "remittance/partials/remittance_row.html",
        {"rem": row},
        request=request,
    )
    toast_html = render_to_string(
        "components/toasts/toast.html",
        {
            "id": int(timezone.now().timestamp() * 1000),
            "message": "Payment status updated.",
            "type": "success",
            "duration": 4000,
        },
        request=request,
    )
    return HttpResponse(row_html + toast_html)
