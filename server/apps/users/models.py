import uuid
import secrets
from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password, check_password

from apps.core.models import Product
from apps.core.managers import TenantQuerySet, TenantManager

class RoleQuerySet(TenantQuerySet):
    def active(self):
        """Returns active roles ordered by their names in alphabetical order."""
        return self.filter(deleted_at__isnull=True).order_by('name')

    def default_roles(self):
        """Returns default roles ordered by their names in alphabetical order."""
        return self.filter(is_default=True).order_by('name')

    def for_user(self, user):
        """Tenant-scoped roles, including shared platform default roles."""
        if user.is_superuser or not hasattr(user, 'company_id') or user.company_id is None:
            return self.all()
        return self.filter(models.Q(company_id=user.company_id) | models.Q(company_id__isnull=True))

class Role(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, default='', blank=True)
    is_default = models.BooleanField(default=False)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='roles',
        db_index=True,
        help_text='NULL = platform-default role template shared across tenants.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = RoleQuerySet.as_manager()

    class Meta:
        db_table = 'users_role'
        verbose_name_plural = 'roles'
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                condition=models.Q(company__isnull=True, deleted_at__isnull=True),
                name='unique_default_role_name',
            ),
            models.UniqueConstraint(
                fields=['company', 'name'],
                condition=models.Q(company__isnull=False, deleted_at__isnull=True),
                name='unique_tenant_role_name',
            ),
        ]

    def __str__(self) -> str:
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
        verbose_name_plural = 'permissions'
        constraints = [
            models.UniqueConstraint(
                fields=['role', 'action'],
                name='unique_permission_role_action',
            ),
        ]

    def __str__(self) -> str:
        return f"{self.role.name} - {self.action}"


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pin = models.CharField(max_length=128, null=True, blank=True)
    role = models.ForeignKey(Role, on_delete=models.RESTRICT, null=True, blank=True)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='users',
        db_index=True,
        help_text='NULL = platform superuser (sees all tenants).',
    )
    daily_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        default=Decimal("0.00"),
        help_text="Fixed daily salary rate for Staff role users. Drivers are commission-based.",
    )
    deactivated_at = models.DateTimeField(null=True, blank=True)
    force_password_change = models.BooleanField(
        default=False,
        help_text="When True, the user must change their password on next login.",
    )
    password_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date after which the user's password is considered expired.",
    )
    pin_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date after which the user's PIN is considered expired.",
    )

    # We will let AbstractUser handle username, email, first_name, last_name, password, is_active, is_staff, is_superuser, last_login, date_joined

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'users_user'
        verbose_name_plural = 'users'
        indexes = [
            models.Index(fields=['company', 'deleted_at', 'deactivated_at', 'is_active']),
        ]

    def set_password(self, raw_password: str) -> None:
        """Hashes the raw password and records its 90-day expiry."""
        super().set_password(raw_password)
        self.password_expires_at = timezone.now() + timedelta(days=90)

    def set_pin(self, raw_pin: str) -> None:
        """Hashes the raw PIN and stores it in the pin field.

        Passing an empty value (``None`` or ``""``) clears the PIN and its
        expiry — useful for resetting a user's PIN during offboarding.
        """
        if not raw_pin:
            self.pin = None
            self.pin_expires_at = None
            return

        if not str(raw_pin).isdigit():
            raise ValueError("PIN must contain only digits.")

        self.pin = make_password(str(raw_pin))
        self.pin_expires_at = timezone.now() + timedelta(days=90)

    def check_pin(self, raw_pin: str) -> bool:
        """Verifies a raw PIN against the stored hash safely.

        Returns ``False`` when no PIN is set, when the input is empty, or
        when the underlying hasher raises an exception (defensive — never
        leaks a crypto error to the caller).
        """
        if not self.pin or not raw_pin:
            return False
        try:
            return check_password(str(raw_pin), self.pin)
        except Exception:
            return False


    def __str__(self) -> str:
        return self.name

    @property
    def full_name(self) -> str:
        """Returns full name if both first and last names are set, otherwise falls back to username."""
        if self.first_name and self.last_name:
            return f"{self.first_name.strip()} {self.last_name.strip()}"
        return self.username

    @property
    def short_name(self) -> str:
        """Returns short name (e.g. J. Doe) if both first and last names are set, otherwise falls back to username."""
        if self.first_name and self.last_name:
            return f"{self.first_name.strip()[0].upper()}. {self.last_name.strip()}"
        return self.username

    @property
    def name(self) -> str:
        """Alias for full_name to maintain backward compatibility."""
        return self.full_name


class DriverCommission(models.Model):
    driver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='commissions')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    rate_per_unit = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    company = models.ForeignKey(
        'settings.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='driver_commissions',
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = 'users_driver_commission'
        verbose_name_plural = 'driver commissions'
        indexes = [
            models.Index(fields=['company', 'driver', 'product']),
            models.Index(fields=['company', 'product']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'driver', 'product'],
                name='unique_driver_commission_company_driver_product',
            ),
        ]

    def __str__(self) -> str:
        return f"Driver commission — {self.product.name}"

