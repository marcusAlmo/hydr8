from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'apps.core'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import Product, SystemConfig
        auditlog.register(Product)
        auditlog.register(SystemConfig)
