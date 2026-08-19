from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("dashboard/", views.dashboard_view, name="dashboard"),
    # HTMX lazy-load partials (skeleton → real content swap)
    path(
        "dashboard/partials/stats/",
        views.dashboard_stats_partial,
        name="dashboard_stats",
    ),
    path(
        "dashboard/partials/recent-remittances/",
        views.dashboard_recent_remittances_partial,
        name="dashboard_recent_remittances",
    ),
    path(
        "dashboard/partials/outstanding-debts/",
        views.dashboard_outstanding_debts_partial,
        name="dashboard_outstanding_debts",
    ),
]
