from django.apps import AppConfig


class SettingsConfig(AppConfig):
    name = 'apps.settings'
    verbose_name = 'Settings'

    def ready(self):
        # Company has been moved to apps.core. The auditlog registration
        # for Company is now handled in apps.core.apps.CoreConfig.ready().
        pass
