from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'apps.core'

    def ready(self):
        from auditlog.registry import auditlog

        from . import lookups  # noqa: F401
        from .models import Product, SystemConfig
        auditlog.register(Product)
        auditlog.register(SystemConfig)
