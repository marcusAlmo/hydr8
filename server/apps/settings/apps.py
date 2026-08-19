from django.apps import AppConfig


class SettingsConfig(AppConfig):
    name = 'apps.settings'
    verbose_name = 'Settings'

    def ready(self):
        from auditlog.registry import auditlog

        from .models import Company
        auditlog.register(Company)
