from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = 'apps.audit'
    verbose_name = 'Audit Log'

    def ready(self):
        # Import signal handlers so they connect to Django's signal bus.
        from . import signals  # noqa: F401
