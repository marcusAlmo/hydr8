import uuid
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils import timezone
from django.db.models import CheckConstraint, Q, UniqueConstraint
from django.db.models.functions import Length
from django.core.exceptions import ObjectDoesNotExist
from apps.core.models import SoftDeleteManagerMixin

# Register Length lookup so we can use __length in Q objects cleanly
models.CharField.register_lookup(Length)


# ==========================================
# 1. MANAGERS
# ==========================================


class RoleManager(SoftDeleteManagerMixin, models.Manager):
    """
    Custom manager for Role model using SoftDeleteQuerySet.
    """
    pass


class CustomUserManager(SoftDeleteManagerMixin, UserManager):
    """
    Custom auth manager inheriting from Django's UserManager and exposing SoftDeleteQuerySet methods.
    """
    pass


# ==========================================
# 3. MODELS
# ==========================================
class Role(models.Model):
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # STANDARD HOOK: Using our custom manager class with explicit type hint
    objects: RoleManager = RoleManager()

    def __str__(self) -> str:
        return str(self.name)
    
    class Meta:
        verbose_name = "Role"
        verbose_name_plural = "Roles"
        constraints = [
            CheckConstraint(
                condition=Q(name__length__gte=2),
                name='role_name_min_length'
            )
        ]


class Permission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    action = models.CharField(max_length=255, help_text="The resource or action being accessed (e.g., 'dashboard', 'users', 'reports')")
    
    can_read = models.BooleanField(default=False)
    can_write = models.BooleanField(default=False)
    can_update = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # STANDARD HOOK: Explicitly define the default manager for strict type checkers
    objects = models.Manager()

    class Meta:
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"
        constraints = [
            UniqueConstraint(
                fields=['role', 'action'],
                name='unique_role_action_permission'
            )
        ]
    def __str__(self):
        return f"{self.role.name} - {self.action}"


class User(AbstractUser):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        DEACTIVATED = 'DEACTIVATED', 'Deactivated'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    role = models.ForeignKey(Role, on_delete=models.RESTRICT, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # STANDARD HOOK: Use the custom UserManager that safely inherits core features
    objects = CustomUserManager()

    @property
    def is_account_active(self):
        return self.status == self.Status.ACTIVE and self.deleted_at is None

    # --- FAT MODEL: BUSINESS LOGIC METHODS ---
    def deactivate(self):
        self.status = self.Status.DEACTIVATED
        self.deleted_at = timezone.now()
        self.updated_at = timezone.now()
        self.save(update_fields=['status', 'deleted_at', 'updated_at'])

    def activate(self):
        self.status = self.Status.ACTIVE
        self.deleted_at = None
        self.updated_at = timezone.now()
        self.save(update_fields=['status', 'deleted_at', 'updated_at'])

    def assign_role(self, role_name):
        try:
            # Look how clean! .active() can now be safely called on Role managers
            role = Role.objects.active().get(name=role_name)
            self.role = role
            self.updated_at = timezone.now()
            self.save(update_fields=['role', 'updated_at'])
            return True
        except ObjectDoesNotExist:
            return False

    def has_permission(self, action, access_type='read'):
        """
        Check if this user's role grants the specified access type for a given action.

        WARNING: This method issues a DB query on every call.
        For bulk permission checks, prefetch 'role__permissions' at the QuerySet level
        in your view or serializer to avoid N+1 queries.
        """
        if not self.role:
            return False
            
        try:
            # Query the Permission model directly to avoid reverse-relation type checker issues
            perm = Permission.objects.get(role=self.role, action=action)
            return getattr(perm, f'can_{access_type}', False)
        except ObjectDoesNotExist:
            return False

    def __str__(self):
        return self.username
    
    class Meta(AbstractUser.Meta):
        verbose_name = "User"
        verbose_name_plural = "Users"
        constraints = [
            # Check constraints for first_name and last_name length
            CheckConstraint(
                condition=Q(first_name__length__gte=3),
                name='user_first_name_min_length'
            ),
            CheckConstraint(
                condition=Q(last_name__length__gte=3),
                name='user_last_name_min_length'
            )
        ]