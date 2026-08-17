from django.apps import AppConfig


class RemittanceConfig(AppConfig):
    name = 'apps.remittance'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import Remittance, RemittanceRider, RemittanceRiderProductLine, Expense, RiderCredit, RiderCreditRepayment
        auditlog.register(Remittance)
        auditlog.register(RemittanceRider)
        auditlog.register(RemittanceRiderProductLine)
        auditlog.register(Expense)
        auditlog.register(RiderCredit)
        auditlog.register(RiderCreditRepayment)
