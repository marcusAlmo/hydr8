from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Company


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
