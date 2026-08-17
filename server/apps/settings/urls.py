from django.urls import path

from . import views

app_name = "settings"

urlpatterns = [
    # Full page
    path("", views.settings_view, name="list"),

    # HTMX POST endpoints
    path("system-config/save/", views.save_system_config_view, name="save_system_config"),
    path("system-config/apply-credit-limit-all/", views.apply_credit_limit_to_all_view, name="apply_credit_limit_all"),
    path("company/save/", views.save_company_view, name="save_company"),
    path("profile/save/", views.save_profile_view, name="save_profile"),
    path("username/change/", views.change_username_view, name="change_username"),
    path("password/change/", views.change_password_view, name="change_password"),
]
