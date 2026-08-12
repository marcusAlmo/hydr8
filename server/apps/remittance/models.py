from django.db import models
from django.conf import settings

from apps.core.managers import TenantManager


class Remittance(models.Model):
    class StatusChoices(models.TextChoices):
        DRAFT = 'DRAFT'
        FINALIZED = 'FINALIZED'

    date = models.DateField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_remittances')
    finalized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='finalized_remittances')
    status = models.CharField(max_length=20, choices=StatusChoices, default=StatusChoices.DRAFT)
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_credit_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_borrowed_items = models.SmallIntegerField(default=0)
    net_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_rider_credits = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_repayments_received = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tithe_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    tithe_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    offering_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tithes_paid = models.BooleanField(default=False)
    offering_paid = models.BooleanField(default=False)
    notes = models.TextField(null=True, blank=True)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='remittances',
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    objects = TenantManager()

    class Meta:
        db_table = 'remittance_remittance'
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'date'],
                name='unique_remittance_company_date',
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'status']),
            models.Index(fields=['company', 'tithes_paid', 'offering_paid']),
        ]

    def __str__(self):
        return f"Remittance {self.date} ({self.status})"


class RemittanceRider(models.Model):
    remittance = models.ForeignKey(Remittance, on_delete=models.CASCADE, related_name='riders')
    rider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='remittance_lines')
    subtotal_payable = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    subtotal_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='remittance_riders',
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = 'remittance_remittance_rider'
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'remittance', 'rider'],
                name='unique_rr_company_remittance_rider',
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'remittance']),
            models.Index(fields=['company', 'rider']),
        ]

    def __str__(self):
        return f"Rider {self.rider.username} for {self.remittance.date}"


class RemittanceRiderProductLine(models.Model):
    remittance_rider = models.ForeignKey(RemittanceRider, on_delete=models.CASCADE, related_name='product_lines')
    product = models.ForeignKey('core.Product', on_delete=models.PROTECT, related_name='remittance_lines')
    qty_sold = models.SmallIntegerField()
    qty_credited = models.SmallIntegerField(default=0)
    borrowed_items = models.SmallIntegerField(default=0)
    unit_price_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    commission_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    subtotal_payable = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal_credit = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal_commission = models.DecimalField(max_digits=12, decimal_places=2)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='remittance_rider_product_lines',
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = 'remittance_remittance_rider_productline'
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'remittance_rider', 'product'],
                name='unique_rrpl_company_rr_product',
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'remittance_rider']),
            models.Index(fields=['company', 'product']),
        ]

    def __str__(self):
        return f"{self.product.name} line for {self.remittance_rider}"


class Expense(models.Model):
    remittance = models.ForeignKey(Remittance, on_delete=models.CASCADE, related_name='expenses')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='expenses',
        db_index=True,
    )
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        db_table = 'remittance_expense'
        indexes = [
            models.Index(fields=['company', 'remittance']),
        ]

    def __str__(self):
        return f"Expense: {self.description} ({self.amount})"


class RiderCredit(models.Model):
    rider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='issued_credits')
    recipient_name = models.CharField(max_length=255)
    customer = models.ForeignKey('customers.Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='rider_credits')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_repaid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_repaid = models.BooleanField(default=False)
    notes = models.TextField(null=True, blank=True)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='rider_credits',
        db_index=True,
    )
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_rider_credits')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = 'remittance_rider_credit'
        indexes = [
            models.Index(fields=['company', 'rider']),
            models.Index(fields=['company', 'is_repaid']),
            models.Index(fields=['company', 'created_at']),
        ]

    def __str__(self):
        return f"Credit of {self.amount} for {self.recipient_name} by {self.rider.username}"


class RiderCreditRepayment(models.Model):
    rider_credit = models.ForeignKey(RiderCredit, on_delete=models.PROTECT, related_name='repayments')
    remittance = models.ForeignKey(Remittance, on_delete=models.CASCADE, related_name='credit_repayments')
    amount_repaid = models.DecimalField(max_digits=12, decimal_places=2)
    commission_applied = models.DecimalField(max_digits=12, decimal_places=2)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='rider_credit_repayments',
        db_index=True,
    )
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_repayments')
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        db_table = 'remittance_rider_credit_repayment'
        indexes = [
            models.Index(fields=['company', 'rider_credit']),
            models.Index(fields=['company', 'remittance']),
        ]

    def __str__(self):
        return f"Repayment of {self.amount_repaid} for {self.rider_credit}"
