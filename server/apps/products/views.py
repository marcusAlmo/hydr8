import json
import logging
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock data — Products & Pricing (catalogue + per-driver commission matrix)
#
# Mirrors the Stitch "Products & Pricing — Hydr8" screen.  The product
# catalogue and rider commission rates are kept in sync with the remittance
# app's ``_mock_add_remittance_data`` so the two prototypes tell a coherent
# story until real backend services are implemented.
#
# Replace ``_mock_products_data`` with real selectors/services once the
# Product / CommissionRate models are ready — the template already consumes
# these context keys.
# ---------------------------------------------------------------------------
def _mock_products_data() -> dict:
    """
    Mock data for the Products & Pricing prototype.

    Field shape mirrors the planned Product model:
      key, name, variation, unit_price, is_active
    and the planned CommissionRate model (per rider x product):
      rider_id, rider_name, initials, avatar_bg, avatar_text,
      driver_code, rates: { product_key: rate }
    """
    # --- Product catalogue (kept in sync with remittance mock data) ---
    # ``is_default`` marks system-default products that are locked from edits
    # and deletion — only non-default products can be edited (after PIN) or
    # removed.  This protects the core catalogue from accidental changes.
    products = [
        {
            "key": "5gal_alk_round",
            "name": "Alkaline Water",
            "variation": "5-Gallon Round",
            "unit_price": "40.00",
            "is_active": True,
            "is_default": True,
            "row_class": "",
            "name_class": "text-on-surface",
            "action_activate": False,  # active row shows edit + deactivate
        },
        {
            "key": "5gal_mineral_slim",
            "name": "Mineral Water",
            "variation": "5-Gallon Slim",
            "unit_price": "35.00",
            "is_active": True,
            "is_default": True,
            "row_class": "",
            "name_class": "text-on-surface",
            "action_activate": False,
        },
        {
            "key": "1gal_dispenser",
            "name": "Purified Drinking Water",
            "variation": "1-Gallon Dispenser",
            "unit_price": "65.00",
            "is_active": True,
            "is_default": True,
            "row_class": "",
            "name_class": "text-on-surface",
            "action_activate": False,
        },
        {
            "key": "350ml_case",
            "name": "PET Bottles",
            "variation": "350ml Case (24 pcs)",
            "unit_price": "120.00",
            "is_active": True,
            "is_default": True,
            "row_class": "",
            "name_class": "text-on-surface",
            "action_activate": False,
        },
        {
            "key": "bulk_tank_100gal",
            "name": "Distilled Water",
            "variation": "Bulk Tank (100 gal)",
            "unit_price": "850.00",
            "is_active": False,
            "is_default": False,  # non-default: can be edited (after PIN) + deleted
            "row_class": "bg-surface-container-low/50",
            "name_class": "text-on-surface-variant",
            "action_activate": True,  # inactive row shows activate + delete
        },
    ]

    # --- Commission matrix column accents (semantic project tokens) ---
    # Maps each product to a coloured underline used in the matrix header.
    # NOTE: amber is rendered with the project's #D97706 warning token rather
    # than Tailwind's amber-500 to stay on-palette with the rest of the app.
    product_columns = [
        {"key": "5gal_alk_round",    "label": "Alkaline (5G)",  "border_class": "border-b-4 border-primary"},
        {"key": "5gal_mineral_slim", "label": "Mineral (5G)",   "border_class": "border-b-4 border-tertiary"},
        {"key": "1gal_dispenser",    "label": "Purified (1G)",  "border_class": "border-b-4 border-[#D97706]"},
        {"key": "350ml_case",        "label": "PET (Case)",     "border_class": "border-b-4 border-secondary"},
        {"key": "bulk_tank_100gal",  "label": "Distilled (Bulk)", "border_class": "border-b-4 border-outline"},
    ]

    # --- Riders + per-product commission rates ---
    # Rates are kept in sync with remittance's ``commission_rates`` so the
    # two prototypes agree on what each rider earns per product.
    #
    # A larger roster (12 drivers) is used so the pagination controls on the
    # commission matrix are visible and testable in the prototype.  When real
    # data replaces this mock, the template's Alpine pagination will work the
    # same way — it slices the rider list client-side at ``page_size``.
    _rider_defs = [
        ("Juan Dela Cruz",     "JC", "DRV-001", "bg-secondary-fixed",      "text-on-secondary-fixed"),
        ("Roberto Santos",     "RS", "DRV-004", "bg-tertiary-fixed",       "text-on-tertiary-fixed"),
        ("Maria Garcia",       "MG", "DRV-012", "bg-primary-fixed",        "text-on-primary-fixed"),
        ("Carlos Reyes",       "CR", "DRV-018", "bg-tertiary-container",   "text-on-tertiary-container"),
        ("Ana Torres",         "AT", "DRV-023", "bg-secondary-container",  "text-on-secondary-container"),
        ("Pedro Lim",          "PL", "DRV-031", "bg-primary-container",    "text-on-primary-container"),
        ("Liza Mendoza",       "LM", "DRV-037", "bg-secondary-fixed",      "text-on-secondary-fixed"),
        ("Ramon Cruz",         "RC", "DRV-044", "bg-tertiary-fixed",       "text-on-tertiary-fixed"),
        ("Diana Villanueva",   "DV", "DRV-052", "bg-primary-fixed",        "text-on-primary-fixed"),
        ("Mark Tan",           "MT", "DRV-058", "bg-tertiary-container",   "text-on-tertiary-container"),
        ("Sofia Ramos",        "SR", "DRV-063", "bg-secondary-container",  "text-on-secondary-container"),
        ("Erik Bautista",      "EB", "DRV-071", "bg-primary-container",    "text-on-primary-container"),
    ]

    # Base rate table — each rider gets a small deterministic offset from the
    # first rider so the matrix shows realistic per-driver variation without
    # hand-typing 60 numbers.
    _base_rates = {
        "5gal_alk_round":      ("5.00",  0.25),
        "5gal_mineral_slim":   ("3.50",  0.15),
        "1gal_dispenser":      ("8.00",  0.30),
        "350ml_case":          ("12.00", 0.40),
        "bulk_tank_100gal":    ("45.00", 1.50),
    }

    riders = []
    for idx, (name, initials, code, bg, txt) in enumerate(_rider_defs):
        rates: dict[str, str] = {}
        for pkey, (base, step) in _base_rates.items():
            # Even-indexed riders get +step, odd get -step, so rates oscillate
            # around the base rather than monotonically increasing.
            delta = step if idx % 2 == 0 else -step
            rates[pkey] = f"{float(base) + delta:.2f}"
        riders.append({
            "id": idx + 1,
            "name": name,
            "initials": initials,
            "avatar_bg": bg,
            "avatar_text": txt,
            "driver_code": code,
            "rates": rates,
        })

    return {
        # --- Top bar ---
        "today_date": datetime.now().strftime("%A, %b %d, %Y"),

        # --- Tabs ---
        "tabs": [
            {"id": "products", "label": "Products", "icon": "inventory_2", "active": True},
            {"id": "commissions", "label": "Delivery Commissions", "icon": "payments", "active": False},
        ],

        # --- Products tab ---
        "products": products,
        "active_count": sum(1 for p in products if p["is_active"]),
        "default_count": sum(1 for p in products if p["is_default"]),
        "total_count": len(products),

        # --- AI pricing insight (mock) ---
        # NOTE: values are kept as plain strings; the template applies the
        # styled <span> wrappers so we never need the |safe filter on this
        # server-generated content.
        "ai_insight": {
            "product_name": "Alkaline Water",
            "region": "South Laguna",
            "delta_pct": "8%",
            "adjustment": "+₱2.00",
            "impact": "₱4,960",
        },

        # --- Commissions tab ---
        # NOTE: ``rate_cells`` is pre-aligned with ``product_columns`` so the
        # template can iterate without a dynamic dict-key lookup filter
        # (Django templates have no built-in ``|lookup``).  This mirrors the
        # "pre-compute in the view" pattern used by the customers stats row.
        "product_columns": product_columns,
        # ``page_size`` controls the client-side Alpine pagination on the
        # rider rows.  ``rider_count`` is the total (pre-pagination) so the
        # template can show "Showing X of Y drivers" without re-counting.
        "page_size": 5,
        "rider_count": len(riders),
        "riders": [
            {
                "id": r["id"],
                "name": r["name"],
                "initials": r["initials"],
                "avatar_bg": r["avatar_bg"],
                "avatar_text": r["avatar_text"],
                "driver_code": r["driver_code"],
                "rate_cells": [
                    {"product_key": c["key"], "rate": r["rates"].get(c["key"], "")}
                    for c in product_columns
                ],
            }
            for r in riders
        ],
    }


def _serialize_for_alpine(data: dict) -> dict:
    """
    Serializes the riders and product_columns lists as JSON strings safe for
    embedding inside an Alpine.js ``x-data`` attribute.

    Single quotes are escaped to ``&#39;`` so they don't break the
    single-quoted attribute boundary — matching the pattern used by the
    remittance trends seed.
    """
    out = dict(data)
    out["riders_json"] = json.dumps(data["riders"]).replace("'", "&#39;")
    out["product_columns_json"] = json.dumps(data["product_columns"]).replace("'", "&#39;")
    # Minimal product list for the Alpine edit table — only the fields the
    # client needs to initialise per-row editable state (no PII, no rates).
    out["products_json"] = json.dumps([
        {"key": p["key"], "name": p["name"], "variation": p["variation"],
         "unit_price": p["unit_price"], "is_default": p["is_default"]}
        for p in data["products"]
    ]).replace("'", "&#39;")
    return out


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def products_pricing_view(request):
    """
    Renders the Products & Pricing management page.

    Currently uses mock data (``_mock_products_data``) to prototype the
    product inventory table and per-driver commission matrix for client
    approval.  When backend services are ready, swap the mock call for real
    selector functions that return the same context shape.
    """
    context = _serialize_for_alpine(_mock_products_data())
    return render(request, "products/products_pricing.html", context)


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
    import json as _json

    try:
        body = _json.loads(request.body)
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
