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
    credit_limit = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
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

    def __str__(self) -> str:
        # RA 10173: Never expose customer names in __str__ for financial models.
        # __str__ appears in admin list views, logs, and repr() output.
        return f"HY-{self.pk:04d}"

    @property
    def is_anomalous(self) -> bool:
        """True if the customer is flagged or blacklisted."""
        return self.status in (self.Status.FLAGGED, self.Status.BLACKLISTED)


class CreditLine(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='credit_lines')
    remittance_rider_product = models.ForeignKey(
        'remittance.RemittanceRiderProductLine',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='credit_lines'
    )
    product = models.ForeignKey('core.Product', on_delete=models.PROTECT)
    qty_credited = models.SmallIntegerField()
    unit_price_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    total_credit_amount = models.DecimalField(max_digits=12, decimal_places=2)
    qty_remaining = models.SmallIntegerField()
    # The user responsible for extending this credit to the customer.
    # May be an admin, staff, or driver — not necessarily the recorder.
    care_of = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='credit_lines_care_of',
        help_text='User responsible for extending this credit (admin/staff/driver).',
    )
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


class BorrowedContainer(models.Model):
    """A single lending event of containers to a customer.

    Tracks each borrowing instance so responsibility can be attributed to
    a specific user (the ``care_of`` field) — admin, staff, or driver —
    rather than only the aggregate counters on ``Customer``.
    """

    class ContainerType(models.TextChoices):
        ROUND_8GAL = 'round_8gal', 'Round 8gal'
        SLIM_8GAL = 'slim_8gal', 'Slim 8gal'
        OTHER = 'other', 'Other'

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='borrowed_containers',
    )
    container_key = models.CharField(
        max_length=20,
        choices=ContainerType.choices,
    )
    qty_borrowed = models.SmallIntegerField()
    qty_returned = models.SmallIntegerField(default=0)
    # The user responsible for lending these containers to the customer.
    # May be an admin, staff, or driver — ensures accountability even when
    # the admin lends directly to a walk-in customer.
    care_of = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='borrowed_containers_care_of',
        help_text='User responsible for lending these containers (admin/staff/driver).',
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_borrowed_containers',
        help_text='User who recorded this borrowing entry.',
    )
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='borrowed_containers',
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = 'customers_borrowed_container'
        indexes = [
            models.Index(fields=['company', 'customer']),
            models.Index(fields=['company', 'care_of']),
        ]

    def __str__(self):
        return f"{self.customer.name} - {self.get_container_key_display()} ({self.qty_remaining} out)"

    @property
    def qty_remaining(self) -> int:
        """Containers still unreturned for this borrowing instance."""
        return max(0, self.qty_borrowed - self.qty_returned)

    @property
    def container_label(self) -> str:
        """Human-readable container label (e.g. ``Round 8gal``)."""
        return self.get_container_key_display()


class CreditPayment(models.Model):
    credit_line = models.ForeignKey(CreditLine, on_delete=models.PROTECT, related_name='payments')
    remittance = models.ForeignKey(
        'remittance.Remittance',
        on_delete=models.PROTECT,
        related_name='credit_payments',
        null=True,
        blank=True,
        help_text='The rider remittance this payment was collected through, if any. '
                  'Null for counter collections recorded via the Collect modal.',
    )
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
