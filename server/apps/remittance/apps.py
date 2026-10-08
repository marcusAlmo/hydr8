from django.apps import AppConfig


class RemittanceConfig(AppConfig):
    name = 'apps.remittance'

    def ready(self):
        from auditlog.registry import auditlog

        from .models import (
            Expense,
            Remittance,
            RemittanceRider,
            RemittanceRiderProductLine,
            RemittanceStaff,
            RiderCredit,
            RiderCreditRepayment,
            RiderDeduction,
            StaffDeduction,
        )
        auditlog.register(Remittance)
        auditlog.register(RemittanceRider)
        auditlog.register(RemittanceRiderProductLine)
        auditlog.register(Expense)
        auditlog.register(RiderCredit)
        auditlog.register(RiderCreditRepayment)
        auditlog.register(RemittanceStaff)
        auditlog.register(StaffDeduction)
        auditlog.register(RiderDeduction)

