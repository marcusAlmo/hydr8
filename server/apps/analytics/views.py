import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.users.permissions import is_admin as user_is_admin

from .selectors import (
    get_outstanding_debts,
    get_recent_remittances,
    get_stats,
    get_today_remittance,
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


def _apply_accent_classes(stats: list[dict]) -> None:
    """Pre-compute border_class / icon_class on each stat dict in-place."""
    for stat in stats:
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]


@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
@login_required
def dashboard_view(request: HttpRequest) -> HttpResponse:
    """Renders the dashboard shell with skeletons.

    Only lightweight data (today_date, today_remittance) is fetched here.
    The heavy sections (stats, recent remittances, outstanding debts) are
    loaded via HTMX lazy-load partials so the user sees the shell + skeleton
    placeholders immediately.

    Restricted to Admin (and platform superusers). Staff users get a focused
    remittance-first view and do not see the dashboard, charts, or reports.
    """
    if not user_is_admin(request.user):
        raise PermissionDenied

    from django.utils import timezone

    context = {
        "today_date": timezone.localtime().strftime("%A, %b %d, %Y"),
        "today_remittance": get_today_remittance(request.user),
    }
    return render(request, "analytics/dashboard.html", context)


# ---------------------------------------------------------------------------
# HTMX lazy-load partials — each returns a single section's content.
# The dashboard shell renders skeleton placeholders that fire `hx-get` to
# these endpoints on load.  Each endpoint only runs its own selector queries.
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
@login_required
def dashboard_stats_partial(request: HttpRequest) -> HttpResponse:
    """Returns the stats row (3 KPI cards) as an HTMX partial."""
    if not user_is_admin(request.user):
        raise PermissionDenied
    stats = get_stats(request.user)
    _apply_accent_classes(stats)
    return render(request, "analytics/partials/stats_row.html", {"stats": stats})


@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
@login_required
def dashboard_recent_remittances_partial(request: HttpRequest) -> HttpResponse:
    """Returns the recent remittances table as an HTMX partial."""
    if not user_is_admin(request.user):
        raise PermissionDenied
    recent = get_recent_remittances(request.user)
    return render(
        request,
        "analytics/partials/recent_remittances.html",
        {"recent_remittances": recent},
    )


@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
@login_required
def dashboard_outstanding_debts_partial(request: HttpRequest) -> HttpResponse:
    """Returns the outstanding debts table as an HTMX partial."""
    if not user_is_admin(request.user):
        raise PermissionDenied
    debts = get_outstanding_debts(request.user)
    return render(
        request,
        "analytics/partials/long_running_debts.html",
        {"outstanding_debts": debts},
    )
