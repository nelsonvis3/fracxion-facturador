from django.contrib import admin

from config.admin import ReadOnlyBusinessAdmin

from .models import Product


@admin.register(Product)
class ProductAdmin(ReadOnlyBusinessAdmin):
    list_display = ("name", "tenant", "sku", "unit_price", "currency", "is_active")
    search_fields = ("name", "sku")
    list_filter = ("is_active", "tenant")
