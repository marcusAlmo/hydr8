from django.urls import path
from . import views

app_name = "remittance"

urlpatterns = [
    path("add/", views.add_remittance_view, name="add"),
    path("history/", views.remittance_history_view, name="history"),
]
