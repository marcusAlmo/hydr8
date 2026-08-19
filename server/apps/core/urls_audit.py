from django.urls import path

from . import views_audit as views

app_name = "audit"

urlpatterns = [
    path("", views.audit_log_view, name="list"),
    path("<int:entry_id>/", views.audit_log_detail_view, name="detail"),
]
