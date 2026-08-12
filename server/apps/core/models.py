from django.db import models
from django.conf import settings
from django.db.models import Q

from apps.core.managers import TenantManager

class Product(models.Model):
    class CategoryChoices(models.TextChoices):
        WATER =  'WATER'
        CONTAINER = 'CONTAINER'
        OTHERS = 'OTHERS'

    name = models.CharField(max_length=100)
    variation = models.CharField(max_length=100, blank=True, null=True)
    category = models.CharField(max_length=100,choices=CategoryChoices, default=CategoryChoices.OTHERS)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='products',
        db_index=True,
    )
    deactivated_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = 'core_product'
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'name', 'variation'],
                condition=Q(deactivated_at__isnull=True),
                name='unique_product_company_name_variation',
            ),
        ]

    @classmethod
    def create(cls, **kwargs):
        name = str(kwargs['name']).title()
        variation = str(kwargs['variation']).title()

    def __str__(self):
        return f"{self.name} - {self.variation}"


class SystemConfigManager(TenantManager):
    def get_value(self, key, default=None):
        try:
            return self.get(key=key).value
        except self.model.DoesNotExist:
            return default


class SystemConfig(models.Model):
    key = models.CharField(max_length=100)
    value = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='system_configs',
        db_index=True,
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    objects = SystemConfigManager()

    class Meta:
        db_table = 'core_system_config'
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'key'],
                name='unique_systemconfig_company_key',
            ),
        ]

    def __str__(self):
        return f"{self.key}: {self.value}"
