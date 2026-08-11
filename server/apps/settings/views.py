import json
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit


# ---------------------------------------------------------------------------
# Mock data — Settings page
#
# Mirrors the Stitch "Settings — Hydr8" screen with four tabs:
#   1. System Config  — operational toggles & rates (lockscreen, tithe rate)
#   2. Company        — business identity (name, contact, email)
#   3. My Profile     — the logged-in user's profile (name, username, password)
#   4. AI Model       — Gemma 2B local model status (size, latency, download)
#
# All values are mock prototypes.  When real backend services are ready,
# swap ``_mock_settings_data`` for real selectors that return the same
# context shape — the templates already consume these keys.
# ---------------------------------------------------------------------------
def _mock_settings_data() -> dict:
    """
    Mock data for the Settings prototype.

    The shape mirrors the planned SystemSetting key-value store, the
    CompanyInfo singleton, the User profile, and the local AI model
    status object.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()

    # --- System Config tab ---
    # Each row maps to a planned SystemSetting record:
    #   key, label, description, type, value, options (for selects)
    # NOTE: MFA / Password Policy toggle was removed — the project does not
    # use MFA.  Password complexity is enforced at the service layer instead.
    system_config = [
        {
            "key": "lockscreen_timeout",
            "label": "Lockscreen Timeout",
            "description": "Minutes of inactivity before force logout.",
            "type": "select",
            "value": "15 min",
            "options": ["5 min", "15 min", "30 min", "Never"],
            "highlight": False,
        },
        {
            "key": "tithe_rate",
            "label": "Tithe Rate (%)",
            "description": "Percentage of net profit allocated to tithes.",
            "type": "number",
            "value": "10.00",
            "highlight": True,  # border-t-2 accent for financial setting
        },
        {
            "key": "approved_credit_limit",
            "label": "Approved Credit Limit (₱)",
            "description": "Maximum outstanding debt a customer can accrue before further credit is blocked.",
            "type": "number",
            "value": "3,000.00",
            "highlight": True,  # border-t-2 accent for financial setting
        },
        {
            "key": "approved_container_limit",
            "label": "Approved Container Borrowing Limit",
            "description": "Maximum total containers (round + slim + other) a customer may have unreturned at once.",
            "type": "number",
            "value": "20",
            "highlight": True,  # border-t-2 accent for operational ceiling
        },
    ]

    # --- Company tab ---
    company = {
        "name": "Hydr8 Logistics International",
        "contact_number": "+63 917 902 1345",
        "email": "ops@hydr8-hq.io",
        "address": "South Laguna Industrial Park, Calamba, Laguna 4027",
    }

    # --- My Profile tab ---
    # Uses the current user if available, falls back to a mock profile.
    # NOTE: Email/SMS alert preferences were removed — the project does not
    # use notification alerts.  Username and password change are included
    # because they are the crucial account credentials.
    profile = {
        "username": "adrian.thorne",
        "first_name": "Adrian",
        "last_name": "Thorne",
        "full_name": "Adrian Thorne",
        "role": "Senior Ops Director",
        "employee_id": "H8-9921",
        "avatar_initials": "AT",
    }

    # --- AI Model tab ---
    # Gemma 2B via @mlc-ai/web-llm (WebGPU, browser-local).
    ai_model = {
        "name": "Gemma 2B",
        "description": "Optimized for logistics forecasting and routing.",
        "status": "Ready",
        "status_class": "bg-tertiary-container/20 text-tertiary border-tertiary/30",
        "model_size": "1.2 GB",
        "latency": "~140ms",
        "last_update": "2h ago",
        "download_progress": 100,
        "download_complete": True,
    }

    # --- Tab definitions ---
    tabs = [
        {"id": "system-config", "label": "System Config", "icon": "tune", "active": True},
        {"id": "company", "label": "Company", "icon": "business", "active": False},
        {"id": "profile", "label": "My Profile", "icon": "account_circle", "active": False},
        {"id": "ai-model", "label": "AI Model", "icon": "smart_toy", "active": False},
    ]

    return {
        "today_date": datetime.now().strftime("%A, %b %d, %Y"),
        "tabs": tabs,
        "system_config": system_config,
        "company": company,
        "profile": profile,
        "ai_model": ai_model,
    }


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def settings_view(request):
    """
    Renders the Settings page with four tabs:
    System Config, Company, My Profile, and AI Model.

    A ``?tab=<tab_id>`` query parameter selects the initially-active tab.
    This is what the sidebar's Profile link uses to deep-link into the
    My Profile tab (``/settings/?tab=profile``).

    Currently uses mock data (``_mock_settings_data``) to prototype the
    settings UI for client approval.  When backend services are ready,
    swap the mock call for real selector functions that return the same
    context shape.
    """
    context = _mock_settings_data()

    # Validate the requested tab against the known tab IDs so an invalid
    # value can't inject arbitrary content into the Alpine x-data attribute.
    valid_tab_ids = {t["id"] for t in context["tabs"]}
    requested_tab = request.GET.get("tab", "").strip()
    context["initial_tab"] = requested_tab if requested_tab in valid_tab_ids else "system-config"

    return render(request, "settings/settings.html", context)
