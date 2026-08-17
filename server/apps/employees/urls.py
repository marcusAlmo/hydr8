from django.urls import path

from . import views

app_name = "employees"

urlpatterns = [
    path("", views.employees_directory_view, name="list"),
    path("search/", views.employees_search_view, name="search"),
    path("user/<str:user_id>/", views.user_detail_view, name="detail"),
]
