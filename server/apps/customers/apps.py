from django.apps import AppConfig


class CustomersConfig(AppConfig):
    name = 'apps.customers'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import Customer, CreditLine, CreditPayment
        auditlog.register(Customer)
        auditlog.register(CreditLine)
        auditlog.register(CreditPayment)
