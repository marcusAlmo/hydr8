import uuid
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils import timezone

class SoftDeleteQuerySet(models.QuerySet):
    """Chainable custom QuerySet for handling soft deletes."""
    def active(self):
        return self.filter(deleted_at__isnull=True)
    
    def deleted(self):
        return self.filter(deleted_at__isnull=False)


class RoleManager(models.Manager):
    """Custom manager that utilizes the SoftDeleteQuerySet."""
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)
    
    def active_roles(self):
        # This replaces the instance method you had before
        return self.get_queryset().active()

class CustomUserManager(UserManager):
    """Custom manager for the User model that utilizes the SoftDeleteQuerySet."""
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)
    
    def active_users(self):
        return self.get_queryset().active()


class Role(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Attach the custom manager
    objects = RoleManager()

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Role"
        verbose_name_plural = "Roles"


class Permission(models.Model):
    """
    Defines the access levels a specific role has for various actions/resources.
    This establishes the Permissions Matrix for RBAC.
    """
    id = models.BigAutoField(primary_key=True)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    action = models.CharField(max_length=255, help_text="The resource or action being accessed (e.g., 'dashboard', 'users', 'reports')")
    
    # Representing RWUD (Read, Write, Update, Delete) access
    can_read = models.BooleanField(default=False)
    can_write = models.BooleanField(default=False)
    can_update = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"
        # Ensure a role only has one permission entry per action
        unique_together = ('role', 'action')

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

    # Attach the custom manager to User as well (since it also has deleted_at)
    objects = CustomUserManager()

    @property
    def is_account_active(self):
        """Derived state based on instance fields."""
        return self.status == self.Status.ACTIVE and self.deleted_at is None

    # --- FAT MODEL: BUSINESS LOGIC METHODS ---
    def deactivate(self):
        """Encapsulate the business logic for deactivating a user."""
        self.status = self.Status.DEACTIVATED
        self.deleted_at = timezone.now()
        self.save(update_fields=['status', 'deleted_at'])

    def activate(self):
        """Encapsulate the business logic for reactivating a user."""
        self.status = self.Status.ACTIVE
        self.deleted_at = None
        self.save(update_fields=['status', 'deleted_at'])

    def assign_role(self, role_name):
        """Encapsulate the logic of finding and assigning a role."""
        try:
            role = Role.objects.get(name=role_name)
            self.role = role
            self.save(update_fields=['role'])
            return True
        except Role.DoesNotExist:
            return False

    def has_permission(self, action, access_type='read'):
        """
        Check if the user has a specific permission (RWUD) via their role.
        """
        if not self.role:
            return False
            
        try:
            perm = self.role.permissions.get(action=action)
            # We use getattr to dynamically check can_read, can_write, etc.
            return getattr(perm, f'can_{access_type}', False)
        except Permission.DoesNotExist:
            return False

    def __str__(self):
        return self.username
    
    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"