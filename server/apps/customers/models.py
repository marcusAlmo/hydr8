from django.db import models
from django.conf import settings

from apps.core.managers import TenantManager


class Customer(models.Model):
    """A water refilling station customer (household, sari-sari, business).

    Status lifecycle:
        ACTIVE → FLAGGED → BLACKLISTED
            ↑___________|
        (anomaly detection promotes to FLAGGED; manual ops can
        BLACKLIST. Reset to ACTIVE requires explicit intervention.)
    """

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        FLAGGED = 'flagged', 'Flagged (Anomalous)'
        BLACKLISTED = 'blacklisted', 'Blacklisted'

    name = models.CharField(max_length=255)
    address = models.TextField(null=True, blank=True)
    contact_number = models.CharField(max_length=20, null=True, blank=True)
    debt_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    borrowed_round_8gal = models.SmallIntegerField(default=0)
    borrowed_slim_8gal = models.SmallIntegerField(default=0)
    borrowed_other = models.SmallIntegerField(default=0)
    last_credit_at = models.DateTimeField(null=True, blank=True)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='customers',
        db_index=True,
    )

    # --- Anomaly / blacklist tracking ---
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    flagged_reason = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Human-readable reason set when status becomes FLAGGED/BLACKLISTED.',
    )
    flagged_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = TenantManager()

    class Meta:
        db_table = 'customers_customer'
        indexes = [
            models.Index(fields=['company', 'debt_balance']),
            models.Index(fields=['company', 'last_credit_at']),
            models.Index(fields=['company', 'status']),
        ]

    def __str__(self):
        return self.name

    @property
    def is_anomalous(self) -> bool:
        """True if the customer is flagged or blacklisted."""
        return self.status in (self.Status.FLAGGED, self.Status.BLACKLISTED)


class CreditLine(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='credit_lines')
    remittance_rider_product = models.ForeignKey(
        'remittance.RemittanceRiderProductLine',
        on_delete=models.PROTECT,
        related_name='credit_lines'
    )
    product = models.ForeignKey('core.Product', on_delete=models.PROTECT)
    qty_credited = models.SmallIntegerField()
    unit_price_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    total_credit_amount = models.DecimalField(max_digits=12, decimal_places=2)
    qty_remaining = models.SmallIntegerField()
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='credit_lines',
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        db_table = 'customers_credit_line'

    def __str__(self):
        return f"{self.customer.name} - {self.product.name} ({self.qty_remaining} left)"


class CreditPayment(models.Model):
    credit_line = models.ForeignKey(CreditLine, on_delete=models.PROTECT, related_name='payments')
    remittance = models.ForeignKey('remittance.Remittance', on_delete=models.PROTECT, related_name='credit_payments')
    containers_paid = models.SmallIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='credit_payments',
        db_index=True,
    )
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        db_table = 'customers_credit_payment'
        indexes = [
            models.Index(fields=['company', 'credit_line']),
            models.Index(fields=['company', 'remittance']),
        ]

    def __str__(self):
        return f"Payment of {self.amount} for {self.credit_line}"
