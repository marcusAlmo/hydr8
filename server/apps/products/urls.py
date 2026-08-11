from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    path("", views.products_pricing_view, name="list"),
    path("verify-pin/", views.verify_pin_view, name="verify_pin"),
]
