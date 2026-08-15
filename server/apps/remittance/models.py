from django.db import models
from django.conf import settings
from decimal import Decimal

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
    total_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_other_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_borrowed_items = models.SmallIntegerField(default=0)
    net_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_remittance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_repayments_received = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tithe_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    tithe_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    offering_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tithes_paid = models.BooleanField(default=False)
    offering_paid = models.BooleanField(default=False)
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
            models.Index(fields=['company', 'date', 'status']),
            models.Index(fields=['company', 'tithes_paid', 'offering_paid']),
        ]

    def __str__(self):
        return f"Remittance {self.date} ({self.status})"


class RemittanceRider(models.Model):
    remittance = models.ForeignKey(Remittance, on_delete=models.CASCADE, related_name='riders')
    rider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='remittance_lines')
    subtotal_payable = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    subtotal_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    commission_override = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    remitted = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
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
    remittance_rider = models.ForeignKey(
        RemittanceRider,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='expenses',
        help_text='When set, this expense is attributed to a specific rider.',
    )
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
            models.Index(fields=['company', 'remittance_rider']),
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


class RiderDeduction(models.Model):
    """A deduction applied to a rider's commission on a remittance.

    Examples: cash advances, shortages, errors, returned-container
    penalties.  Each deduction reduces the rider's net commission.
    """
    remittance_rider = models.ForeignKey(
        RemittanceRider,
        on_delete=models.CASCADE,
        related_name='deductions',
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='rider_deductions',
        db_index=True,
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_rider_deductions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        db_table = 'remittance_rider_deduction'
        indexes = [
            models.Index(fields=['company', 'remittance_rider']),
        ]

    def __str__(self):
        return f"Deduction: {self.description} ({self.amount}) for {self.remittance_rider}"


class RemittanceStaff(models.Model):
    """A staff member's payment record on a remittance.

    Stores the salary paid to a staff member for the remittance date,
    including any operator override of their default ``daily_rate`` and
    the computed net pay after deductions.
    """
    remittance = models.ForeignKey(Remittance, on_delete=models.CASCADE, related_name='staff_payments')
    staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='remittance_staff_lines')
    daily_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    salary_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='remittance_staff',
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = 'remittance_remittance_staff'
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'remittance', 'staff'],
                name='unique_rs_company_remittance_staff',
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'remittance']),
            models.Index(fields=['company', 'staff']),
        ]

    def __str__(self):
        return f"Staff {self.staff.username} for {self.remittance.date}"

    @property
    def effective_salary(self) -> Decimal:
        """Returns the override if set, otherwise the daily_rate snapshot."""
        if self.salary_override is not None:
            return self.salary_override
        return self.daily_rate_snapshot


class StaffDeduction(models.Model):
    """A deduction applied to a staff member's pay on a remittance.

    Examples: cash advances, shortages, errors.
    """
    remittance_staff = models.ForeignKey(
        RemittanceStaff,
        on_delete=models.CASCADE,
        related_name='deductions',
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='staff_deductions',
        db_index=True,
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_staff_deductions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        db_table = 'remittance_staff_deduction'
        indexes = [
            models.Index(fields=['company', 'remittance_staff']),
        ]

    def __str__(self):
        return f"Deduction: {self.description} ({self.amount}) for {self.remittance_staff}"
