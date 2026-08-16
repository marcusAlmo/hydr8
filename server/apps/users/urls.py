from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password/change/', views.password_change_view, name='password_change'),
    path('password/change/submit/', views.password_change_submit_view, name='password_change_submit'),
    path('onboarding/', views.onboarding_view, name='onboarding'),
    path('onboarding/submit/', views.onboarding_submit_view, name='onboarding_submit'),
    path('lock/', views.screen_lock_view, name='screen_lock'),
    path('lock/arm/', views.screen_lock_arm_view, name='screen_lock_arm'),
    path('lock/submit/', views.screen_lock_submit_view, name='screen_lock_submit'),
    path('lock/verify/', views.screen_lock_verify_view, name='screen_lock_verify'),
    path('user/<uuid:user_id>/temp-password/', views.generate_temp_password_view, name='generate_temp_password'),
    path('user/<uuid:user_id>/edit/', views.edit_user_view, name='edit_user'),
    path('user/<uuid:user_id>/edit/submit/', views.edit_user_submit_view, name='edit_user_submit'),
    path('user/<uuid:user_id>/delete/', views.delete_user_view, name='delete_user'),
    path('user/add/', views.add_user_view, name='add_user'),
    path('user/add/submit/', views.add_user_submit_view, name='add_user_submit'),
]