import uuid
import secrets
from datetime import timedelta

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password, check_password

from apps.core.models import Product


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
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pin = models.CharField(max_length=128, null=True, blank=True)
    role = models.ForeignKey(Role, on_delete=models.RESTRICT, null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    
    # We will let AbstractUser handle username, email, first_name, last_name, password, is_active, is_staff, is_superuser, last_login, date_joined
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'users_user'

    def set_pin(self, raw_pin: str) -> None:
        """Hashes the raw PIN and stores it in the pin field."""
        if not raw_pin:
            raise ValueError("A valid PIN must be provided.")
            
        if not str(raw_pin).isdigit():
            raise ValueError("PIN must contain only digits.")
            
        self.pin = make_password(str(raw_pin))

    def check_pin(self, raw_pin: str) -> bool:
        """Verifies a raw PIN against the stored hash safely."""
        if not self.pin or not raw_pin:
            return False
        return check_password(str(raw_pin), self.pin)


    def __str__(self):
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users_driver_commission'
        unique_together = ('driver', 'product')

    def __str__(self):
        return f"{self.driver.username} - {self.product.name}"


class UserRefreshTokenQuerySet(models.QuerySet):
    def active(self):
        """Returns tokens that have not expired and have not been revoked."""
        return self.filter(expires_at__gt=timezone.now(), revoked_at__isnull=True).order_by('-expires_at')

    def expired(self):
        """Returns tokens that have past their expiration date."""
        return self.filter(expires_at__lte=timezone.now()).order_by('-expires_at')

    def revoke(self):
        """Revokes all active tokens in the current queryset in a single query."""
        return self.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())


class UserRefreshToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    refresh_token = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    replaced_with = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)

    objects = UserRefreshTokenQuerySet.as_manager()

    class Meta:
        db_table = 'users_refresh_token'

    @classmethod
    def generate_token(cls, user):
        """Generates a new refresh token for the user with an expiry from settings."""
        expiry_days = getattr(settings, 'REFRESH_TOKEN_EXPIRY_DAYS', 7)
        expires_at = timezone.now() + timedelta(days=expiry_days)
        
        new_token = cls.objects.create(
            user=user,
            refresh_token=secrets.token_urlsafe(32),
            expires_at=expires_at
        )

        previous_token = cls.objects.filter(user=user).exclude(pk=new_token.pk).order_by('-expires_at').first()

        if previous_token:
            previous_token.replaced_with = new_token
            previous_token.save(update_fields=['replaced_with'])

        # Revoke all previous active tokens for this specific user
        cls.objects.filter(user=user).exclude(pk=new_token.pk).active().revoke()

        return new_token
    def __str__(self):
        return f"{self.user.username} - {self.refresh_token}"