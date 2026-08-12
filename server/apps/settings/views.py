import logging

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.core.views import (
    error_message,
    toast_error,
    toast_for_exception,
    toast_success,
)

from .forms import (
    CompanyForm,
    PasswordChangeForm,
    ProfileForm,
    UsernameChangeForm,
)
from .selectors import get_settings_context
from .services import (
    change_password,
    change_username,
    save_company,
    save_system_config,
    update_profile,
)

logger = logging.getLogger(__name__)

# Keys accepted by the System Config save endpoint (whitelist).
_SYSTEM_CONFIG_KEYS = (
    'lockscreen_timeout_minutes',
    'tithe_rate',
    'approved_credit_limit',
    'approved_container_limit',
)


# ---------------------------------------------------------------------------
# Full page — Settings
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def settings_view(request):
    """Renders the Settings page with four tabs.

    A ``?tab=<tab_id>`` query parameter selects the initially-active tab.
    The sidebar's Profile link uses this to deep-link into the My Profile
    tab (``/settings/?tab=profile``).
    """
    context = get_settings_context(request.user)

    # Validate the requested tab against the known tab IDs so an invalid
    # value can't inject arbitrary content into the Alpine x-data attribute.
    valid_tab_ids = {t["id"] for t in context["tabs"]}
    requested_tab = request.GET.get("tab", "").strip()
    context["initial_tab"] = requested_tab if requested_tab in valid_tab_ids else "system-config"

    return render(request, "settings/settings.html", context)


# ---------------------------------------------------------------------------
# HTMX POST endpoints
# ---------------------------------------------------------------------------
# Each endpoint follows the same pattern:
#   1. Validate the form / inputs.
#   2. Call the corresponding service.
#   3. On success: return a toast partial (OOB swap into #toast-container).
#   4. On failure: return an error toast partial with status 400.
#
# Rate limits follow AGENTS.md:
#   - 30/m for standard writes (system config, company, profile)
#   - 10/m for sensitive credential changes (username, password)

def _success_response(request, message: str) -> HttpResponse:
    """Returns the shared success toast component for OOB swap into #toast-container."""
    return toast_success(request, message)


def _error_response(request, message: str, status: int = 400) -> HttpResponse:
    """Returns the shared error toast component for OOB swap into #toast-container."""
    return toast_error(request, message, status=status)


def _is_admin(user) -> bool:
    """Returns True if the user may edit system/company settings."""
    return bool(user.is_staff or user.is_superuser)


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def save_system_config_view(request):
    """HTMX endpoint — saves one or more System Config keys.

    Accepts form-encoded fields keyed by the SystemConfig key name
    (e.g. ``tithe_rate=10.00``).  Only whitelisted keys are accepted.
    Restricted to admin/staff users.
    """
    if not _is_admin(request.user):
        return _error_response(request, "Only administrators can edit system config.", status=403)

    errors = []
    saved_keys = []
    for key in _SYSTEM_CONFIG_KEYS:
        if key not in request.POST:
            continue
        display_value = request.POST.get(key, '')
        try:
            save_system_config(
                key=key,
                display_value=display_value,
                performed_by=request.user,
            )
            saved_keys.append(key)
        except ValidationError as exc:
            errors.append(f"{key}: {error_message(exc)}")

    if errors:
        return _error_response(request, " | ".join(errors))
    if not saved_keys:
        return _error_response(request, "No settings were submitted.")

    return _success_response(request, "System configuration saved successfully.")


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def save_company_view(request):
    """HTMX endpoint — saves the tenant Company record.

    Restricted to admin/staff users.
    """
    if not _is_admin(request.user):
        return _error_response(request, "Only administrators can edit company details.", status=403)

    form = CompanyForm(request.POST)
    if not form.is_valid():
        msgs = [f"{k}: {v[0]}" for k, v in form.errors.items()]
        return _error_response(request, " | ".join(msgs))

    try:
        save_company(
            user=request.user,
            name=form.cleaned_data['name'],
            contact_number=form.cleaned_data['contact_number'],
            email=form.cleaned_data['email'],
            address=form.cleaned_data['address'],
        )
    except ValidationError as exc:
        return toast_for_exception(request, exc)

    return _success_response(request, "Company details saved successfully.")


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def save_profile_view(request):
    """HTMX endpoint — saves the logged-in user's first/last name."""
    form = ProfileForm(request.POST)
    if not form.is_valid():
        msgs = [f"{k}: {v[0]}" for k, v in form.errors.items()]
        return _error_response(request, " | ".join(msgs))

    update_profile(
        user=request.user,
        first_name=form.cleaned_data['first_name'],
        last_name=form.cleaned_data['last_name'],
    )
    return _success_response(request, "Profile saved successfully.")


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def change_username_view(request):
    """HTMX endpoint — changes the username (current-password verified)."""
    form = UsernameChangeForm(request.POST)
    if not form.is_valid():
        msgs = [f"{k}: {v[0]}" for k, v in form.errors.items()]
        return _error_response(request, " | ".join(msgs))

    try:
        change_username(
            user=request.user,
            current_password=form.cleaned_data['current_password'],
            new_username=form.cleaned_data['new_username'],
        )
    except ValidationError as exc:
        return toast_for_exception(request, exc)

    return _success_response(request, "Username changed successfully.")


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def change_password_view(request):
    """HTMX endpoint — self-service password change (current-password verified).

    Keeps the user's session alive via ``update_session_auth_hash`` so
    they are not logged out after changing their password.
    """
    form = PasswordChangeForm(request.POST)
    if not form.is_valid():
        msgs = [f"{k}: {v[0]}" for k, v in form.errors.items()]
        return _error_response(request, " | ".join(msgs))

    try:
        change_password(
            user=request.user,
            current_password=form.cleaned_data['current_password'],
            new_password=form.cleaned_data['new_password'],
        )
    except ValidationError as exc:
        return toast_for_exception(request, exc)

    # Keep the session alive — otherwise the password change logs the
    # user out and the HTMX response triggers a redirect to login.
    update_session_auth_hash(request, request.user)

    return _success_response(request, "Password changed successfully.")
