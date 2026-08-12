import logging
from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .selectors import get_dashboard_context

if TYPE_CHECKING:
    pass

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

# Tag variant → Tailwind classes for AI insight tag chips.
_TAG_VARIANT_CLASSES = {
    "primary": "bg-surface-container-high text-primary border border-primary/10",
    "error": "bg-error/10 text-error border border-error/10",
    "neutral": "bg-surface-container-high text-on-secondary-fixed-variant border border-outline-variant/30",
}

# AI insight card variant → container classes.
_INSIGHT_VARIANT_CLASSES = {
    "primary": "bg-primary-container/5 border border-primary-container/10 hover:bg-primary-container/10",
    "error": "bg-error/5 border border-error/10 hover:bg-error/10",
}


@require_http_methods(["GET"])
@ratelimit(key="user", rate="120/m", method="GET", block=True)
@login_required
def dashboard_view(request: HttpRequest) -> HttpResponse:
    """Renders the main analytics dashboard from live operational data."""
    context = get_dashboard_context(request.user)

    # Pre-compute accent classes so the template stays clean.
    for stat in context["stats"]:
        accent = _ACCENT_CLASSES.get(stat["accent"], _ACCENT_CLASSES["primary"])
        stat["border_class"] = accent["border"]
        stat["icon_class"] = accent["icon"]

    # Pre-compute tag and card classes for AI insights.
    for insight in context["ai_insights"]:
        insight["card_class"] = _INSIGHT_VARIANT_CLASSES.get(
            insight["variant"], _INSIGHT_VARIANT_CLASSES["primary"]
        )
        for tag in insight["tags"]:
            tag["class"] = _TAG_VARIANT_CLASSES.get(
                tag["variant"], _TAG_VARIANT_CLASSES["neutral"]
            )

    return render(request, "analytics/dashboard.html", context)
