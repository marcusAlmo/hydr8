import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.users.permissions import is_admin as user_is_admin

from .presentation_employees import (
    build_employee_directory_context,
    build_roles_permissions_context,
    build_user_detail_context,
)
from .selectors_employees import (
    get_employee_directory_data,
    get_roles_permissions_data,
    get_user_detail_data,
)

logger = logging.getLogger(__name__)


def _can_view_employees(user) -> bool:
    """Admin role (and platform superusers) may view the directory.

    Staff users get a focused remittance/customers view and do not access
    the Employees & Users directory.
    """
    return user_is_admin(user)


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
def employees_directory_view(request):
    """Renders the full Employees & Users directory with live data."""
    if not _can_view_employees(request.user):
        return HttpResponse("Forbidden", status=403)

    directory_ctx = build_employee_directory_context(
        get_employee_directory_data(request.user)
    )
    roles_ctx = build_roles_permissions_context(
        get_roles_permissions_data(request.user)
    )
    context = {**directory_ctx, **roles_ctx}
    return render(request, "employees/employees_directory.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def user_detail_view(request, user_id: str):
    """HTMX endpoint — returns the expanded report partial for a specific user."""
    if not _can_view_employees(request.user):
        return HttpResponse("Forbidden", status=403)

    data = get_user_detail_data(request.user, user_id)
    if data is None:
        return HttpResponse("User not found.", status=404)

    context = build_user_detail_context(data)
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

    context = build_employee_directory_context(
        get_employee_directory_data(request.user, query, page)
    )
    return render(request, "employees/partials/users_table.html", context)
