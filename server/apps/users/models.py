import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser


class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'users_role'

    def __str__(self):
        return self.name


class Permission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='permissions')
    action = models.CharField(max_length=100)
    can_read = models.BooleanField(default=False)
    can_write = models.BooleanField(default=False)
    can_update = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_permission'
        unique_together = ('role', 'action')

    def __str__(self):
        return f"{self.role.name} - {self.action}"


class User(AbstractUser):
    class StatusChoices(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        DEACTIVATED = 'DEACTIVATED', 'Deactivated'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pin = models.CharField(max_length=128, null=True, blank=True)
    role = models.ForeignKey(Role, on_delete=models.RESTRICT, null=True, blank=True)
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.ACTIVE)
    
    # We will let AbstractUser handle username, email, first_name, last_name, password, is_active, is_staff, is_superuser, last_login, date_joined
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'users_user'

    def __str__(self):
        return self.username


class DriverCommission(models.Model):
    driver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='commissions')
    product = models.ForeignKey('core.Product', on_delete=models.CASCADE)
    rate_per_unit = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_drivercommission'
        unique_together = ('driver', 'product')

    def __str__(self):
        return f"{self.driver.username} - {self.product.name}"