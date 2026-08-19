import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.users.permissions import is_admin as user_is_admin

from . import selectors
from .presentation import (
    apply_accent_classes,
    build_container_breakdown,
    build_outstanding_debt_row,
    build_recent_remittance_row,
    build_stats_cards,
    build_today_remittance_status,
    format_sales_trend,
)

logger = logging.getLogger(__name__)


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

    rem = selectors.get_today_remittance(request.user)
    context = {
        "today_date": timezone.localtime().strftime("%A, %b %d, %Y"),
        "today_remittance": build_today_remittance_status(rem),
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

    today_sales = selectors.get_today_sales(request.user)
    yesterday_sales = selectors.get_yesterday_sales(request.user)
    trend, direction = format_sales_trend(today_sales, yesterday_sales)
    outstanding = selectors.get_outstanding_debt(request.user)
    counts = selectors.get_unreturned_container_counts(request.user)
    containers = build_container_breakdown(
        counts["round"], counts["slim"], counts["other"]
    )

    stats = build_stats_cards(
        today_sales=today_sales,
        sales_trend=trend,
        sales_direction=direction,
        outstanding_debt=outstanding,
        containers=containers,
    )
    apply_accent_classes(stats)
    return render(request, "analytics/partials/stats_row.html", {"stats": stats})


@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
@login_required
def dashboard_recent_remittances_partial(request: HttpRequest) -> HttpResponse:
    """Returns the recent remittances table as an HTMX partial."""
    if not user_is_admin(request.user):
        raise PermissionDenied
    raw_rows = selectors.get_recent_remittances(request.user)
    recent = [build_recent_remittance_row(r) for r in raw_rows]
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
    credits = selectors.get_outstanding_debt_credits(request.user)
    today = timezone.localdate()
    debts = [build_outstanding_debt_row(c, today) for c in credits]
    return render(
        request,
        "analytics/partials/long_running_debts.html",
        {"outstanding_debts": debts},
    )
