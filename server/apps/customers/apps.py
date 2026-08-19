from django.apps import AppConfig


class CustomersConfig(AppConfig):
    name = 'apps.customers'

    def ready(self):
        from auditlog.registry import auditlog

        from .models import BorrowedContainer, CreditLine, CreditPayment, Customer
        auditlog.register(Customer)
        auditlog.register(CreditLine)
        auditlog.register(CreditPayment)
        auditlog.register(BorrowedContainer)
        # Import signal handlers so they are registered at startup.
        from . import signals  # noqa: F401
