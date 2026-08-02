from django.db import models


class DailySnapshot(models.Model):
    snapshot_date = models.DateField(unique=True)
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_credit_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tithe_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_borrowed_items = models.SmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'analytics_dailysnapshot'

    def __str__(self):
        return f"Snapshot for {self.snapshot_date}"
