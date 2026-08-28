from django.urls import path

from . import views

app_name = "customers"

urlpatterns = [
    path("", views.customer_list_view, name="list"),
    path("table/", views.customer_table_view, name="table"),
    path("ranking/top-payers/", views.top_payers_view, name="top_payers"),
    path("ranking/prompt-returners/", views.prompt_returners_view, name="prompt_returners"),
    path("add/", views.customer_add_view, name="add"),
    path("add/submit/", views.customer_add_submit_view, name="add_submit"),
    path("record-debt/", views.record_debt_view, name="record_debt"),
    path("record-debt/submit/", views.record_debt_submit_view, name="record_debt_submit"),
    path("record-borrowed/", views.record_borrowed_view, name="record_borrowed"),
    path("record-borrowed/submit/", views.record_borrowed_submit_view, name="record_borrowed_submit"),
    path("<str:customer_id>/edit/", views.customer_edit_view, name="edit"),
    path("<str:customer_id>/edit/submit/", views.customer_edit_submit_view, name="edit_submit"),
    path("<str:customer_id>/", views.customer_detail_view, name="detail"),
    path("<str:customer_id>/history/", views.customer_history_view, name="history"),
    path("<str:customer_id>/history/<str:item_id>/edit/", views.customer_history_edit_view, name="history_edit"),
    path("<str:customer_id>/history/<str:item_id>/edit/submit/", views.customer_history_edit_submit_view, name="history_edit_submit"),
    path("<str:customer_id>/history/<str:item_id>/delete/", views.customer_history_delete_view, name="history_delete"),
    path("<str:customer_id>/history/<str:item_id>/delete/submit/", views.customer_history_delete_submit_view, name="history_delete_submit"),
    path("<str:customer_id>/collect/", views.customer_collect_view, name="collect"),
    path("<str:customer_id>/collect/submit/", views.customer_collect_submit_view, name="collect_submit"),
    path("<str:customer_id>/delete/", views.customer_delete_view, name="delete"),
]
