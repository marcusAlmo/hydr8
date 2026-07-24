from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Role, Permission, User

@admin.register(Role)
class RoleAdmin(ModelAdmin):
    list_display = ('name', 'created_at', 'updated_at')

@admin.register(Permission)
class PermissionAdmin(ModelAdmin):
    list_display = ('role', 'action', 'can_read', 'can_write', 'can_update', 'can_delete')
    list_filter = ('role', 'action', 'can_read', 'can_write', 'can_update', 'can_delete')
    search_fields = ('role__name', 'action')

@admin.register(User)
class UserAdmin(ModelAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'status', 'is_account_active')
    list_filter = ('role', 'status', 'is_superuser', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')
