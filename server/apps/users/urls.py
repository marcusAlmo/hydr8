from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('password/change/', views.password_change_view, name='password_change'),
    path('password/change/submit/', views.password_change_submit_view, name='password_change_submit'),
    path('user/<uuid:user_id>/temp-password/', views.generate_temp_password_view, name='generate_temp_password'),
    path('user/<uuid:user_id>/edit/', views.edit_user_view, name='edit_user'),
    path('user/<uuid:user_id>/edit/submit/', views.edit_user_submit_view, name='edit_user_submit'),
]