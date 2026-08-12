from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    path("", views.products_pricing_view, name="list"),
    path("verify-pin/", views.verify_pin_view, name="verify_pin"),
    path("save/", views.products_save_view, name="save"),
    path("commission/save/", views.commission_save_view, name="commission_save"),
    path("commission/bulk-set/", views.commission_bulk_set_view, name="commission_bulk_set"),
]
