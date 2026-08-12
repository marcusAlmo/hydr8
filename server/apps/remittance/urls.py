from django.urls import path
from . import views

app_name = "remittance"

urlpatterns = [
    path("add/", views.add_remittance_view, name="add"),
    path("create/", views.create_remittance_view, name="create"),
    path("clear-draft/", views.clear_draft_view, name="clear_draft"),
    path("check-date/", views.check_remittance_date_view, name="check_date"),
    path("history/", views.remittance_history_view, name="history"),
    path(
        "<int:remittance_id>/paid-status/",
        views.update_paid_status_view,
        name="update_paid_status",
    ),
    path(
        "<int:remittance_id>/finalize/",
        views.finalize_remittance_view,
        name="finalize",
    ),
]
