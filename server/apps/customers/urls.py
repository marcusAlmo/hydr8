from django.urls import path
from . import views

app_name = "customers"

urlpatterns = [
    path("", views.customer_list_view, name="list"),
    path("table/", views.customer_table_view, name="table"),
    path("debt/", views.debt_table_view, name="debt_table"),
    path("add/", views.customer_add_view, name="add"),
    path("add/submit/", views.customer_add_submit_view, name="add_submit"),
    path("record-debt/", views.record_debt_view, name="record_debt"),
    path("record-debt/submit/", views.record_debt_submit_view, name="record_debt_submit"),
    path("record-borrowed/", views.record_borrowed_view, name="record_borrowed"),
    path("record-borrowed/submit/", views.record_borrowed_submit_view, name="record_borrowed_submit"),
    path("<str:customer_id>/edit/", views.customer_edit_view, name="edit"),
    path("<str:customer_id>/edit/submit/", views.customer_edit_submit_view, name="edit_submit"),
    path("<str:customer_id>/", views.customer_detail_view, name="detail"),
    path("<str:customer_id>/collect/", views.customer_collect_view, name="collect"),
    path("<str:customer_id>/collect/submit/", views.customer_collect_submit_view, name="collect_submit"),
    path("<str:customer_id>/delete/", views.customer_delete_view, name="delete"),
]
