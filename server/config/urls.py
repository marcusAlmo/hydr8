"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from apps.core.views import health_check_view

urlpatterns = [
    path('health/', health_check_view, name='health_check'),
    path('healthz/', health_check_view, name='healthz_check'),
    path('up/', health_check_view, name='up_check'),
    path('admin/', admin.site.urls),
    path('', include('apps.users.urls')),
    path('analytics/', include('apps.analytics.urls')),
    path('remittance/', include('apps.remittance.urls')),
    path('customers/', include('apps.customers.urls')),
    path('products/', include('apps.products.urls')),
    path('employees/', include('apps.users.urls_employees')),
    path('settings/', include('apps.settings.urls')),
    path('audit/', include('apps.core.urls_audit')),
]

# Custom error handlers — render friendly fragments for common errors.
handler403 = 'apps.users.views.ratelimited_view'
handler404 = 'apps.core.views.handler404_view'
handler500 = 'apps.core.views.handler500_view'
