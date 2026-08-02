from django.apps import AppConfig


class UsersConfig(AppConfig):
    """
    Application configuration for the users app.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'
    label = 'users'
