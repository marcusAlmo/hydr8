from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Role, Permission, User, DriverCommission

@admin.register(Role)
class RoleAdmin(ModelAdmin):
    list_display = ('name', 'created_at', 'updated_at')
    search_fields = ('name',)
    fieldsets = (
        ("Role Details", {
            "fields": ("name",)
        }),
    )

@admin.register(Permission)
class PermissionAdmin(ModelAdmin):
    list_display = ('role', 'action', 'can_read', 'can_write', 'can_update', 'can_delete')
    list_filter = ('role', 'action', 'can_read', 'can_write', 'can_update', 'can_delete')
    search_fields = ('role__name', 'action')
    fieldsets = (
        ("Resource Assignment", {
            "fields": ("role", "action"),
            "classes": ["tab"],
        }),
        ("Access Levels (RWUD)", {
            "fields": ("can_read", "can_write", "can_update", "can_delete"),
            "classes": ["tab"],
        }),
    )

@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):  # type: ignore
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_active')
    list_filter = ('role', 'is_active', 'is_superuser', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    
    fieldsets = (
        ("Authentication", {
            "fields": ("username", "password"),
            "classes": ["tab"],
        }),
        ("Personal Information", {
            "fields": ("first_name", "last_name", "email"),
            "classes": ["tab"],
        }),
        ("Role & Deactivation", {
            "fields": ("role", "deactivated_at"),
            "classes": ["tab"],
        }),
        ("Django Permissions", {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            ),
            "classes": ["tab"],
        }),
        ("Important Dates", {
            "fields": ("last_login", "date_joined", "deleted_at"),
            "classes": ["tab"],
        }),
    )

@admin.register(DriverCommission)
class DriverCommissionAdmin(ModelAdmin):
    list_display = ('driver', 'product', 'rate_per_unit', 'updated_at')
    list_filter = ('product',)
    search_fields = ('driver__username', 'product__name')

