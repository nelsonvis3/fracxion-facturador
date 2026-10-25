from django.contrib import admin

from config.admin import ReadOnlyBusinessAdmin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(ReadOnlyBusinessAdmin):
    list_display = ("name", "tenant", "document_type", "document_number", "is_active")
    search_fields = ("name", "document_number")
    list_filter = ("is_active", "tenant")
