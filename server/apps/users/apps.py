from django.apps import AppConfig


class UsersConfig(AppConfig):
    """
    Application configuration for the users app.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'
    label = 'users'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import User, Role, Permission, DriverCommission
        auditlog.register(User)
        auditlog.register(Role)
        auditlog.register(Permission)
        auditlog.register(DriverCommission)
