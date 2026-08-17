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
    is_default = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Marks system-default products locked from edits and deletion.",
    )
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='products',
        db_index=True,
    )
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = 'core_product'
        verbose_name = 'product'
        verbose_name_plural = 'products'
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'name', 'variation'],
                condition=Q(deactivated_at__isnull=True, deleted_at__isnull=True),
                name='unique_product_company_name_variation',
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'deleted_at']),
            models.Index(fields=['company', 'deactivated_at']),
            models.Index(fields=['company', 'is_default', 'name', 'variation']),
        ]

    @property
    def is_active(self) -> bool:
        return self.deactivated_at is None and self.deleted_at is None

    def save(self, *args, **kwargs):
        """Normalize name and variation casing before persistence."""
        if self.name:
            self.name = str(self.name).title()
        if self.variation:
            self.variation = str(self.variation).title()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} - {self.variation}"


class SystemConfigManager(TenantManager):
    def get_value(self, key, default=None, *, company=None):
        """Returns a SystemConfig value for the tenant, falling back to global.

        Searches the tenant-scoped row first (``company``), then the global
        row (``company=None``), and finally returns ``default`` if neither
        exists. This prevents ``MultipleObjectsReturned`` in multi-tenant
        deployments and makes the lookup explicit for callers.
        """
        try:
            return self.get(key=key, company=company).value
        except self.model.DoesNotExist:
            if company is not None:
                try:
                    return self.get(key=key, company=None).value
                except self.model.DoesNotExist:
                    pass
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
        verbose_name = 'system config'
        verbose_name_plural = 'system configs'
        indexes = [
            models.Index(fields=['key', 'company']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'key'],
                name='unique_systemconfig_company_key',
            ),
        ]

    def __str__(self) -> str:
        return f"{self.key}: {self.value}"
