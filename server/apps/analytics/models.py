from django.db import models

from apps.core.managers import TenantManager


class DailySnapshot(models.Model):
    snapshot_date = models.DateField()
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_credit_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tithe_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    offering_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_borrowed_items = models.SmallIntegerField(default=0)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='daily_snapshots',
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        db_table = 'analytics_daily_snapshot'
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'snapshot_date'],
                name='unique_dailysnapshot_company_date',
            ),
        ]

    def __str__(self):
        return f"Snapshot for {self.snapshot_date}"
