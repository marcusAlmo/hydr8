from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Company, Product, SystemConfig


@admin.register(Company)
class CompanyAdmin(ModelAdmin):
    list_display = ('name', 'contact_number', 'email', 'created_at', 'updated_at', 'deleted_at')
    search_fields = ('name', 'email')
    readonly_fields = ('created_at', 'updated_at', 'deleted_at')
    fieldsets = (
        ("Business Identity", {
            "fields": (
                "name",
                "contact_number",
                "email",
                "address",
            ),
            "classes": ["tab"],
        }),
        ("Audit Metadata", {
            "fields": ("created_at", "updated_at", "deleted_at"),
            "classes": ["tab"],
        }),
    )


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = (
        'name', 'variation', 'category', 'price',
        'company', 'is_default', 'deactivated_at', 'deleted_at',
    )
    search_fields = ('name', 'variation', 'description')
    list_filter = ('category', 'is_default')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SystemConfig)
class SystemConfigAdmin(ModelAdmin):
    list_display = ('key', 'value', 'company', 'updated_at', 'updated_by')
    search_fields = ('key', 'value')
    readonly_fields = ('updated_at',)
