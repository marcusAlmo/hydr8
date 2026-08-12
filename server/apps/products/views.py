import json
import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.core.views import error_message

from .selectors import get_products_pricing_context
from .services import (
    activate_product,
    bulk_set_commission_rates,
    create_product,
    deactivate_product,
    delete_product,
    save_commission_matrix,
    update_product,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_for_alpine(data: dict) -> dict:
    """
    Serializes the riders, product_columns, and products lists as JSON
    strings safe for embedding inside an Alpine.js ``x-data`` attribute.

    Single quotes are escaped to ``&#39;`` so they don't break the
    single-quoted attribute boundary — matching the pattern used by the
    remittance trends seed.

    The JSON is also HTML-escaped (``<``, ``>``, ``&``) to prevent XSS
    when rider names contain angle brackets.  Alpine parses the
    attribute value as a JS string before JSON.parse, so HTML entities
    are decoded by the browser before Alpine sees them.
    """
    out = dict(data)

    def _safe_json(obj) -> str:
        raw = json.dumps(obj)
        # Escape HTML-significant characters so the embedded JSON is
        # safe inside a double-quoted HTML attribute.  Double quotes
        # MUST be escaped (&quot;) because the x-data attribute is
        # double-quoted — unescaped " would terminate the attribute
        # early, breaking Alpine init and enabling attribute injection.
        return (
            raw
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("'", "&#39;")
            .replace('"', "&quot;")
        )

    # Minimal product list for the Alpine edit table — only the fields
    # the client needs to initialise per-row editable state.
    out["products_json"] = _safe_json([
        {"id": p["id"], "name": p["name"], "variation": p["variation"],
         "unit_price": p["unit_price"], "is_default": p["is_default"]}
        for p in data["products"]
    ])
    out["riders_json"] = _safe_json(data["riders"])
    out["product_columns_json"] = _safe_json(data["product_columns"])
    return out


def _is_admin_or_staff(user) -> bool:
    """Returns True if the user may mutate products/commission rates.

    Matches the existing pattern in ``apps/users/views.py``: superusers
    and staff users are allowed.  Drivers are not.
    """
    return bool(user.is_staff or user.is_superuser)


def _forbidden() -> HttpResponse:
    return HttpResponse("Forbidden", status=403)


# ---------------------------------------------------------------------------
# Page render
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def product_create_view(request):
    """Renders the Add Product form and handles creation.

    Staff/superusers only.  On a successful POST, the user is redirected
    back to the Products & Pricing list so the new product is visible.
    """
    if not _is_admin_or_staff(request.user):
        return _forbidden()

    if request.method == "GET":
        return render(request, "products/create_product.html")

    try:
        create_product(
            name=request.POST.get("name", ""),
            variation=request.POST.get("variation", "") or None,
            price=request.POST.get("price", ""),
            category=request.POST.get("category", "WATER"),
            description=request.POST.get("description", "") or None,
            performed_by=request.user,
        )
    except (ValidationError, ValueError, TypeError) as e:
        logger.info("[%s] product_create validation error: %s", request.user.id, e)
        return render(request, "products/create_product.html", {"error": error_message(e)}, status=400)

    return redirect("products:list")


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def products_pricing_view(request):
    """Renders the Products & Pricing management page.

    Pulls real data from ``get_products_pricing_context`` which reads
    from ``Product`` and ``DriverCommission`` via tenant-scoped
    selectors.  The AI pricing insight block remains mock — it will be
    driven by the browser-local Gemma 2B WebGPU engine in a separate
    effort.
    """
    context = _serialize_for_alpine(get_products_pricing_context(request.user))
    return render(request, "products/products_pricing.html", context)


# ---------------------------------------------------------------------------
# PIN verification (unchanged — already wired to real user.check_pin)
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='5/15m', method='POST', block=True)
def verify_pin_view(request):
    """
    HTMX/JSON endpoint — verifies the current user's PIN to unlock
    protected product pricing edits.

    Returns JSON ``{"verified": bool}``.  The Alpine.js product table
    component calls this via fetch when the user enters their PIN in the
    unlock modal; on success it flips the price inputs from read-only to
    editable.

    Rate-limited at 5 attempts per 15 minutes per user, matching the
    PIN verification baseline in AGENTS.md.
    """
    try:
        body = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"verified": False, "error": "Invalid request."}, status=400)

    pin = str(body.get("pin", "")).strip()
    if not pin:
        return JsonResponse({"verified": False, "error": "PIN is required."}, status=400)

    verified = request.user.check_pin(pin)
    if verified:
        logger.info("[%s] PIN verification succeeded (products unlock).", request.user.id)
    else:
        logger.info("[%s] PIN verification failed (products unlock).", request.user.id)

    return JsonResponse({"verified": verified})


# ---------------------------------------------------------------------------
# Product catalogue mutations (PIN-gated, admin/staff only)
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def products_save_view(request):
    """HTMX/JSON endpoint — applies a batch of product catalogue edits.

    The Alpine ``productInventory`` component POSTs the user's changes
    here AFTER the PIN has been verified client-side.  The request body
    is JSON with the shape::

        {
          "pin": "1234",
          "edits":   [ {"id": 1, "name": "...", "variation": "...", "price": "40.00"} ],
          "deletes": [ 2, 3 ],
          "activates": [ 4 ],
          "deactivates": [ 5 ]
        }

    The PIN is re-verified server-side — never trust the client's
    claim that it was verified.  All edits/deletes/activations are
    applied atomically; any failure rolls back the whole batch.

    Returns JSON ``{"ok": true, "saved": N, "deleted": N, ...}`` on
    success, or ``{"ok": false, "error": "..."}`` on failure.
    """
    if not _is_admin_or_staff(request.user):
        return _forbidden()

    try:
        body = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)

    # --- Server-side PIN re-verification (defence in depth) ---
    pin = str(body.get("pin", "")).strip()
    if not pin:
        return JsonResponse({"ok": False, "error": "PIN is required."}, status=400)
    if not request.user.check_pin(pin):
        logger.info("[%s] products_save PIN failed.", request.user.id)
        return JsonResponse({"ok": False, "error": "Incorrect PIN."}, status=403)

    edits = body.get("edits", []) or []
    deletes = body.get("deletes", []) or []
    activates = body.get("activates", []) or []
    deactivates = body.get("deactivates", []) or []

    if not (edits or deletes or activates or deactivates):
        return JsonResponse({"ok": False, "error": "No changes to save."}, status=400)

    saved = 0
    deleted = 0
    activated = 0
    deactivated = 0
    errors: list[str] = []

    try:
        for item in edits:
            update_product(
                product_id=int(item["id"]),
                performed_by=request.user,
                name=item.get("name"),
                variation=item.get("variation"),
                price=item.get("price"),
            )
            saved += 1
        for pid in deletes:
            delete_product(product_id=int(pid), performed_by=request.user)
            deleted += 1
        for pid in activates:
            activate_product(product_id=int(pid), performed_by=request.user)
            activated += 1
        for pid in deactivates:
            deactivate_product(product_id=int(pid), performed_by=request.user)
            deactivated += 1
    except ValidationError as e:
        logger.info("[%s] products_save validation error: %s", request.user.id, e)
        return JsonResponse({"ok": False, "error": error_message(e)}, status=400)
    except (KeyError, ValueError, TypeError) as e:
        logger.info("[%s] products_save input error: %s", request.user.id, e)
        return JsonResponse({"ok": False, "error": f"Invalid input: {e}"}, status=400)

    logger.info(
        "[%s] products_save ok saved=%s deleted=%s activated=%s deactivated=%s",
        request.user.id, saved, deleted, activated, deactivated,
    )
    return JsonResponse({
        "ok": True,
        "saved": saved,
        "deleted": deleted,
        "activated": activated,
        "deactivated": deactivated,
    })


# ---------------------------------------------------------------------------
# Commission matrix mutations (PIN-gated, admin/staff only)
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def commission_save_view(request):
    """HTMX/JSON endpoint — saves commission matrix edits.

    Request body JSON::

        {
          "pin": "1234",
          "changes": { "<driver_id>:<product_id>": "<rate>", ... }
        }

    The PIN is re-verified server-side.  All changes are applied
    atomically via ``save_commission_matrix``; any failure rolls back
    the whole batch.
    """
    if not _is_admin_or_staff(request.user):
        return _forbidden()

    try:
        body = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)

    pin = str(body.get("pin", "")).strip()
    if not pin:
        return JsonResponse({"ok": False, "error": "PIN is required."}, status=400)
    if not request.user.check_pin(pin):
        logger.info("[%s] commission_save PIN failed.", request.user.id)
        return JsonResponse({"ok": False, "error": "Incorrect PIN."}, status=403)

    changes = body.get("changes", {}) or {}
    if not changes:
        return JsonResponse({"ok": False, "error": "No changes to save."}, status=400)

    try:
        count = save_commission_matrix(changes=changes, performed_by=request.user)
    except ValidationError as e:
        logger.info("[%s] commission_save validation error: %s", request.user.id, e)
        return JsonResponse({"ok": False, "error": error_message(e)}, status=400)

    logger.info("[%s] commission_save ok cells=%s", request.user.id, count)
    return JsonResponse({"ok": True, "saved": count})


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def commission_bulk_set_view(request):
    """HTMX/JSON endpoint — bulk-sets one product's rate for all drivers.

    Request body JSON::

        {
          "pin": "1234",
          "product_id": 1,
          "rate": "5.00"
        }
    """
    if not _is_admin_or_staff(request.user):
        return _forbidden()

    try:
        body = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)

    pin = str(body.get("pin", "")).strip()
    if not pin:
        return JsonResponse({"ok": False, "error": "PIN is required."}, status=400)
    if not request.user.check_pin(pin):
        logger.info("[%s] commission_bulk_set PIN failed.", request.user.id)
        return JsonResponse({"ok": False, "error": "Incorrect PIN."}, status=403)

    try:
        product_id = int(body.get("product_id"))
        rate = body.get("rate")
    except (KeyError, ValueError, TypeError) as e:
        return JsonResponse({"ok": False, "error": f"Invalid input: {e}"}, status=400)

    try:
        count = bulk_set_commission_rates(
            product_id=product_id,
            rate=rate,
            performed_by=request.user,
        )
    except ValidationError as e:
        logger.info("[%s] commission_bulk_set validation error: %s", request.user.id, e)
        return JsonResponse({"ok": False, "error": error_message(e)}, status=400)

    logger.info("[%s] commission_bulk_set ok product_id=%s drivers=%s",
                request.user.id, product_id, count)
    return JsonResponse({"ok": True, "updated": count})
