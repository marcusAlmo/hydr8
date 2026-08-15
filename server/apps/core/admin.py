from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Product, SystemConfig


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
