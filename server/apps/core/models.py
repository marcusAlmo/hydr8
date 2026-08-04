from django.db import models
from django.conf import settings

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
    deactivated_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_product'
        unique_together = ('name', 'variation')

    @classmethod
    def create(cls, **kwargs):
        name = str(kwargs['name']).title()
        variation = str(kwargs['variation']).title()

    def __str__(self):
        return f"{self.name} - {self.variation}"


class SystemConfigManager(models.Manager):
    def get_value(self, key, default=None):
        try:
            return self.get(key=key).value
        except self.model.DoesNotExist:
            return default


class SystemConfig(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    objects = SystemConfigManager()

    class Meta:
        db_table = 'core_system_config'

    def __str__(self):
        return f"{self.key}: {self.value}"
