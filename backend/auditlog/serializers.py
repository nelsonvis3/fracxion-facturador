from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    """Representación de solo lectura de un evento de auditoría."""

    tenant = serializers.UUIDField(
        source="tenant_id",
        read_only=True,
        allow_null=True,
    )

    actor = serializers.CharField(
        source="actor.email",
        read_only=True,
        allow_null=True,
    )

    action_label = serializers.CharField(
        source="get_action_display",
        read_only=True,
    )

    class Meta:
        model = AuditEvent

        fields = [
            "id",
            "tenant",
            "actor",
            "action",
            "action_label",
            "entity_type",
            "entity_id",
            "changes",
            "metadata",
            "request_id",
            "occurred_at",
        ]

        read_only_fields = fields
