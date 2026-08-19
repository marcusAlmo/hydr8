import json
import logging
from datetime import date

from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.core.views import error_message, toast_for_exception

from . import selectors
from .presentation import (
    build_add_remittance_context,
    build_recent_remittances,
    build_remittance_history_context,
    build_remittance_row,
    build_remittance_summary,
)
from .services import (
    create_remittance,
    delete_draft_remittance,
    finalize_remittance,
    is_admin_user,
    save_remittance_draft,
    update_remittance_paid_status,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@login_required
@never_cache
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def add_remittance_view(request):
    """Renders the 'Add Remittance' workflow page with live product/rider data.

    Accepts an optional ``date`` query parameter (ISO ``YYYY-MM-DD``) so
    the history page's "Finalize" button can deep-link to a draft for a
    specific date.  When omitted, defaults to today.
    """
    target_date = None
    date_str = request.GET.get("date")
    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except (ValueError, TypeError):
            target_date = None

    context = build_add_remittance_context(request.user, remittance_date=target_date)
    riders = context["riders"]
    products = context["products"]

    selected_rider_id = next(
        (r["id"] for r in riders if r.get("selected")),
        riders[0]["id"] if riders else None,
    )

    context["alpine_seed"] = json.dumps({
        "riders": riders,
        "products": products,
        "repayments": context["repayments"],
        "totalCredits": context.get("total_credits", 0),
        "staff": context.get("staff", []),
        "otherSales": context.get("other_sales", 0),
        "titheRate": context["tithe_rate"],
        "manualOffering": context["offering_amount"],
        "selectedRiderId": selected_rider_id,
        "remittanceDate": context["default_date"],
        "hasDraft": context.get("has_draft", False),
    }).replace("'", "&#39;")

    context["is_admin"] = is_admin_user(user=request.user)
    context["verify_pin_url"] = reverse("remittance:verify_pin")

    return render(request, "remittance/add_remittance.html", context)


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def create_remittance_view(request):
    """HTMX/JSON endpoint — creates a remittance from the Alpine.js form
    payload.

    The ``mode`` field in the JSON body controls the outcome:
      - ``"draft"``    — saves as a draft (staff and admin can do this).
      - ``"finalize"`` — saves and immediately finalizes; requires the
                         Admin role and a valid ``pin``.

    For ``finalize`` mode the PIN is verified *before* the remittance is
    created so a wrong PIN leaves nothing behind.
    """
    try:
        body = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)

    mode = body.get("mode", "draft")

    # --- Guard: only admins can finalize --------------------------------
    if mode == "finalize":
        if not is_admin_user(user=request.user):
            return JsonResponse(
                {"ok": False, "error": "Only administrators can finalize remittances."},
                status=403,
            )
        if not request.user.check_pin(body.get("pin", "")):
            logger.info("[%s] finalize PIN mismatch", request.user.id)
            return JsonResponse(
                {"ok": False, "error": "Incorrect PIN."},
                status=400,
            )

    remittance_date = timezone.localdate()
    remittance_date_str = body.get("remittanceDate")
    if remittance_date_str:
        try:
            remittance_date = date.fromisoformat(str(remittance_date_str))
        except (ValueError, TypeError):
            logger.info("[%s] invalid remittance date: %s", request.user.id, remittance_date_str)
            return JsonResponse({"ok": False, "error": "Invalid remittance date."}, status=400)
    if remittance_date > timezone.localdate():
        logger.info("[%s] future remittance date: %s", request.user.id, remittance_date)
        return JsonResponse({"ok": False, "error": "Remittance date cannot be in the future."}, status=400)

    try:
        if mode == "finalize":
            create_remittance(
                performed_by=request.user,
                riders_data=body.get("riders", []) or [],
                expenses_data=body.get("expenses", []) or [],
                manual_offering=body.get("manualOffering", "0"),
                tithe_rate=body.get("titheRate", "0.10"),
                remittance_date=remittance_date,
                finalize=True,
                other_sales=body.get("otherSales", 0),
                staff_data=body.get("staff", []) or [],
            )
        else:
            # Draft mode uses the upsert so a staff member can save,
            # refresh, edit, and save again without "already exists" errors.
            save_remittance_draft(
                performed_by=request.user,
                riders_data=body.get("riders", []) or [],
                expenses_data=body.get("expenses", []) or [],
                manual_offering=body.get("manualOffering", "0"),
                tithe_rate=body.get("titheRate", "0.10"),
                remittance_date=remittance_date,
                other_sales=body.get("otherSales", 0),
                staff_data=body.get("staff", []) or [],
            )
    except ValidationError as e:
        logger.info("[%s] create remittance validation error: %s", request.user.id, e)
        return JsonResponse({"ok": False, "error": error_message(e)}, status=400)
    except (KeyError, ValueError, TypeError) as e:
        logger.info("[%s] create remittance input error: %s", request.user.id, e)
        return JsonResponse({"ok": False, "error": f"Invalid input: {e}"}, status=400)

    # Finalize always lands on the history page (admin-only surface).
    if mode == "finalize":
        return JsonResponse({"ok": True, "redirect_url": reverse("remittance:history")})

    # Draft mode: admins are sent to the history page (where the draft
    # row appears for them to finalize).  Staff cannot access history, so
    # we keep them on the Add Remittance page and let the client show a
    # "Draft saved" confirmation with the date and an Add Remittance
    # button instead of redirecting them to a Forbidden page.
    if is_admin_user(user=request.user):
        return JsonResponse({"ok": True, "redirect_url": reverse("remittance:history")})

    logger.info(
        "[%s] Draft saved for date=%s (staff; no redirect).",
        request.user.id, remittance_date,
    )
    return JsonResponse({
        "ok": True,
        "draft_saved": True,
        "remittance_date": remittance_date.isoformat(),
    })


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='5/15m', method='POST', block=True)
def verify_pin_view(request):
    """JSON endpoint — verifies the current user's PIN before finalizing a
    remittance.

    Used by the Alpine.js PIN modal on the Add Remittance page.  The
    modal opens when the admin clicks "Confirm & Finalize"; only after
    the PIN is verified here does the client POST the actual finalize
    payload to ``remittance:create`` (which re-verifies the PIN
    server-side as defence in depth).

    Shares the ``pin_attempts`` session counter with the screen-lock
    flows (``users:screen_lock_verify`` etc.) so the three surfaces
    cannot be used to bypass each other's attempt ceiling.

    Returns JSON::

        {"verified": true}                          # on success
        {"verified": false, "attempts_left": 2}     # on wrong PIN
        {"verified": false, "logged_out": true,
         "redirect": "/users/"}                     # after 3 failures

    After 3 failed attempts the user is logged out (session destroyed)
    and the client redirects to the login page — matching the rule on
    the standalone screen-lock page.
    """
    try:
        body = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return JsonResponse(
            {"verified": False, "error": "Invalid request."}, status=400,
        )

    pin = str(body.get("pin", "")).strip()
    if not pin:
        return JsonResponse(
            {"verified": False, "error": "PIN is required."}, status=400,
        )

    user = request.user
    attempts = request.session.get('pin_attempts', 0)

    if user.check_pin(pin):
        request.session.pop('pin_attempts', None)
        logger.info("[%s] Remittance finalize PIN verified.", user.id)
        return JsonResponse({"verified": True})

    attempts += 1
    request.session['pin_attempts'] = attempts

    if attempts >= 3:
        logger.warning(
            "[%s] Remittance finalize PIN exceeded 3 attempts; logging out.",
            user.id,
        )
        auth_logout(request)
        return JsonResponse(
            {
                "verified": False,
                "logged_out": True,
                "redirect": reverse('users:index'),
            },
        )

    logger.info("[%s] Remittance finalize PIN failed (attempt %s).", user.id, attempts)
    return JsonResponse(
        {"verified": False, "attempts_left": 3 - attempts},
    )


@login_required
@never_cache
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

    exists = selectors.remittance_exists_for_date(request.user, target_date)
    status = selectors.remittance_status_for_date(request.user, target_date)

    # Only return credit data when the date is available for a new/ draft
    # remittance.  A FINALIZED date is locked — no need to send credit
    # data the form can't use.
    credit_data = None
    if status != "FINALIZED":
        credit_data = selectors.get_remittance_date_data(request.user, target_date)

    # When a remittance exists (draft or finalized), attach a full
    # read-only summary so the frontend can display the saved record
    # below the date field.  For drafts, the summary also carries a
    # ``draft_state`` the "Load draft" button can apply to the form.
    summary = None
    if exists:
        summary = build_remittance_summary(request.user, target_date)

    return JsonResponse({
        "ok": True,
        "exists": exists,
        "status": status,
        "repayments": credit_data["repayments"] if credit_data else [],
        "total_credits": credit_data["total_credits"] if credit_data else 0,
        "credit_repaid_counts": credit_data["credit_repaid_counts"] if credit_data else {},
        "summary": summary,
    })


@login_required
@never_cache
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def remittance_history_view(request):
    """Renders the 'Remittance History' list page with live DB-backed data.

    Restricted to Admin (and platform superusers). Staff users do not see
    completed records, charts, or financial reports — they work in the
    Add Remittance page (draft + create) only.
    """
    if not is_admin_user(user=request.user):
        return HttpResponse("Forbidden", status=403)
    context = build_remittance_history_context(request.user)
    recent = build_recent_remittances(request.user)

    total = recent["total"]
    shown = len(recent["remittances"])
    per_page = 25
    total_pages = max(1, (total + per_page - 1) // per_page)

    context["remittances"] = recent["remittances"]
    context["is_admin"] = is_admin_user(user=request.user)
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

    row = build_remittance_row(request.user, remittance_id)
    if row is None:
        return toast_for_exception(
            request, ValidationError("Remittance not found.")
        )

    row_html = render_to_string(
        "remittance/partials/remittance_row.html",
        {"rem": row, "is_admin": is_admin_user(user=request.user)},
        request=request,
    )
    response = HttpResponse(row_html)
    response["HX-Trigger"] = json.dumps({
        "showToast": {"msg": "Payment status updated.", "type": "success"},
    })
    return response


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def finalize_remittance_view(request, remittance_id: int):
    """HTMX endpoint — finalizes a DRAFT remittance after PIN verification.

    Any user with the ``Admin`` role (or superuser) may finalize a draft
    prepared by any staff member.  The PIN is verified against the
    *current* user's stored PIN hash.

    On success, returns the refreshed row partial plus a success toast.
    On failure, returns the unchanged row partial plus an error toast so
    the row is not lost from the table.
    """
    pin = request.POST.get("pin", "")
    admin = is_admin_user(user=request.user)

    try:
        finalize_remittance(
            performed_by=request.user,
            remittance_id=remittance_id,
            pin=pin,
        )
    except ValidationError as exc:
        logger.info("[%s] finalize error remittance_id=%s: %s",
                    request.user.id, remittance_id, error_message(exc))
        row = build_remittance_row(request.user, remittance_id)
        row_html = (
            render_to_string(
                "remittance/partials/remittance_row.html",
                {"rem": row, "is_admin": admin},
                request=request,
            )
            if row
            else ""
        )
        response = HttpResponse(row_html, status=400)
        response["HX-Trigger"] = json.dumps({
            "showToast": {"msg": error_message(exc), "type": "error", "duration": 6000},
        })
        return response

    row = build_remittance_row(request.user, remittance_id)
    if row is None:
        return toast_for_exception(
            request, ValidationError("Remittance not found.")
        )

    row_html = render_to_string(
        "remittance/partials/remittance_row.html",
        {"rem": row, "is_admin": admin},
        request=request,
    )
    response = HttpResponse(row_html)
    response["HX-Trigger"] = json.dumps({
        "showToast": {"msg": "Remittance finalized.", "type": "success"},
    })
    return response


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def clear_draft_view(request):
    """JSON endpoint — deletes a DRAFT remittance for a given date.

    Called by the "Clear Draft" button on the Add Remittance page.  This
    removes the DB draft (if any) so the user can start fresh.  The
    client-side localStorage cache is cleared separately by the JS.

    Accepts a JSON body: ``{"remittanceDate": "2026-08-12"}``

    Returns ``{"ok": true, "deleted": bool}`` on success or
    ``{"ok": false, "error": "..."}`` on failure.
    """
    try:
        body = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)

    remittance_date = timezone.localdate()
    date_str = body.get("remittanceDate")
    if date_str:
        try:
            remittance_date = date.fromisoformat(str(date_str))
        except (ValueError, TypeError):
            return JsonResponse({"ok": False, "error": "Invalid date."}, status=400)

    try:
        deleted = delete_draft_remittance(
            performed_by=request.user,
            remittance_date=remittance_date,
        )
    except ValidationError as exc:
        logger.info("[%s] clear draft error: %s", request.user.id, error_message(exc))
        return JsonResponse({"ok": False, "error": error_message(exc)}, status=400)

    return JsonResponse({"ok": True, "deleted": deleted})
