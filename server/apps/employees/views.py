import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .selectors import (
    get_employee_directory_context,
    get_roles_permissions_context,
    get_user_detail_context,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Accent colour mapping for summary cards.
# Maps the `accent` key in a stat dict to the Tailwind classes used in the
# template (border-top colour + icon colour).
# ---------------------------------------------------------------------------
_ACCENT_CLASSES = {
    "primary": {"border": "border-t-primary", "icon": "text-primary"},
    "warning": {"border": "border-t-[#D97706]", "icon": "text-[#D97706]"},
    "error": {"border": "border-t-error", "icon": "text-error"},
    "tertiary": {"border": "border-t-tertiary", "icon": "text-tertiary"},
}


def _apply_accent(stats: list[dict]) -> None:
    """Mutates stat dicts in place, adding ``border_class`` and ``icon_class``."""
    for stat in stats:
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]


def _can_view_employees(user) -> bool:
    """Django built-in RBAC check for the employees directory."""
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.has_perm("users.view_user")
    )


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
def employees_directory_view(request):
    """Renders the full Employees & Users directory with live data."""
    if not _can_view_employees(request.user):
        return HttpResponse("Forbidden", status=403)

    directory_ctx = get_employee_directory_context(request.user)
    roles_ctx = get_roles_permissions_context(request.user)
    context = {**directory_ctx, **roles_ctx}
    _apply_accent(context["stats"])
    return render(request, "employees/employees_directory.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def user_detail_view(request, user_id: str):
    """HTMX endpoint — returns the expanded report partial for a specific user."""
    if not _can_view_employees(request.user):
        return HttpResponse("Forbidden", status=403)

    context = get_user_detail_context(request.user, user_id)
    if context is None:
        return HttpResponse("User not found.", status=404)

    for stat in context.get("driver_stats", []):
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]
    for stat in context.get("staff_stats", []):
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]

    return render(request, "employees/partials/user_detail.html", context)
