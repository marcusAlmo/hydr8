import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password, check_password


class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, default='', blank=True)
    is_default = models.BooleanField(default=False)
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

    def set_pin(self, raw_pin: str) -> None:
        """Hashes the raw PIN and stores it in the pin field."""
        if raw_pin:
            self.pin = make_password(raw_pin)
        else:
            self.pin = None

    def check_pin(self, raw_pin: str) -> bool:
        """Verifies a raw PIN against the stored hash safely."""
        if not self.pin or not raw_pin:
            return False
        try:
            return check_password(str(raw_pin), self.pin)
        except Exception:
            return False

    def __str__(self):
        return self.name

    @property
    def name(self) -> str:
        """Returns full name if available, otherwise falls back to username."""
        full = f"{self.first_name} {self.last_name}".strip()
        return full if full else self.username


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