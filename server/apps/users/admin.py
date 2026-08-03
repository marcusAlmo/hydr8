from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Role, Permission, User, DriverCommission, UserRefreshToken

@admin.register(Role)
class RoleAdmin(ModelAdmin):
    list_display = ('name', 'is_default', 'description', 'created_at', 'updated_at', 'deleted_at')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at', 'deleted_at')
    fieldsets = (
        ("Role Details", {
            "fields": (
                ("name", "is_default"),
                "description",
            ),
            "classes": ["tab"],
        }),
        ("Audit Metadata", {
            "fields": ("created_at", "updated_at", "deleted_at"),
            "classes": ["tab"],
        }),
    )

@admin.register(Permission)
class PermissionAdmin(ModelAdmin):
    list_display = ('role', 'action', 'can_read', 'can_write', 'can_update', 'can_delete', 'updated_at')
    list_filter = ('role', 'action', 'can_read', 'can_write', 'can_update', 'can_delete')
    search_fields = ('role__name', 'action')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ("Resource Assignment", {
            "fields": ("role", "action"),
            "classes": ["tab"],
        }),
        ("Access Levels (RWUD)", {
            "fields": (("can_read", "can_write"), ("can_update", "can_delete")),
            "classes": ["tab"],
        }),
        ("Audit Metadata", {
            "fields": ("created_at", "updated_at"),
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
    readonly_fields = ('pin', 'last_login', 'date_joined', 'created_at', 'updated_at', 'deleted_at')

    fieldsets = (
        ("Authentication & Security", {
            "fields": (("username", "password"), "pin"),
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
        ("Important Dates & Audit", {
            "fields": (
                ("last_login", "date_joined"),
                ("created_at", "updated_at", "deleted_at"),
            ),
            "classes": ["tab"],
        }),
    )

@admin.register(DriverCommission)
class DriverCommissionAdmin(ModelAdmin):
    list_display = ('driver', 'product', 'rate_per_unit', 'created_at', 'updated_at')
    list_filter = ('product',)
    search_fields = ('driver__username', 'product__name')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ("Commission Details", {
            "fields": (
                ("driver", "product"),
                "rate_per_unit",
            ),
            "classes": ["tab"],
        }),
        ("Audit Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ["tab"],
        }),
    )

@admin.register(UserRefreshToken)
class UserRefreshTokenAdmin(ModelAdmin):
    list_display = ('user', 'refresh_token', 'expires_at', 'revoked_at', 'replaced_with', 'created_at')
    list_filter = ('revoked_at', 'expires_at')
    search_fields = ('user__username', 'user__email', 'refresh_token')
    readonly_fields = ('id', 'refresh_token', 'created_at', 'expires_at', 'revoked_at', 'replaced_with')
    fieldsets = (
        ("Token Information", {
            "fields": (
                "user",
                "refresh_token",
                ("expires_at", "revoked_at"),
                "replaced_with",
            ),
            "classes": ["tab"],
        }),
        ("Audit Metadata", {
            "fields": ("id", "created_at"),
            "classes": ["tab"],
        }),
    )
