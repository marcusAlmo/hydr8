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

    return render(request, "employees/partials/user_detail.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
def employees_search_view(request):
    """HTMX endpoint — returns the filtered+paginated users table partial."""
    if not _can_view_employees(request.user):
        return HttpResponse("Forbidden", status=403)

    query = request.GET.get("q", "")
    try:
        page = int(request.GET.get("page", 1))
    except (TypeError, ValueError):
        page = 1

    context = get_employee_directory_context(request.user, query, page)
    return render(request, "employees/partials/users_table.html", context)
