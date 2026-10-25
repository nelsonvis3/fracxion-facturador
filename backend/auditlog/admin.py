from django.contrib import admin

from config.admin import ReadOnlyBusinessAdmin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(ReadOnlyBusinessAdmin):
    list_display = ("occurred_at", "tenant", "actor", "action", "entity_type")
    list_filter = ("action", "tenant")
