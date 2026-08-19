from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'apps.core'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import Product, SystemConfig
        auditlog.register(Product)
        auditlog.register(SystemConfig)
        # Import audit signal handlers so they connect to Django's signal bus.
        from . import signals_audit  # noqa: F401
