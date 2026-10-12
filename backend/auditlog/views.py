from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter

from tenancy.mixins import TenantQuerySetMixin

from .models import AuditEvent
from .permissions import AuditReadPermission
from .serializers import AuditEventSerializer


class AuditEventViewSet(
    TenantQuerySetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """
    API de consulta del historial de auditoría.

    Solo permite listar y consultar eventos de la empresa
    autorizada. No ofrece creación, modificación ni eliminación.
    """

    queryset = AuditEvent.objects.select_related(
        "tenant",
        "actor",
    ).all()

    serializer_class = AuditEventSerializer

    permission_classes = [
        AuditReadPermission,
    ]

    filter_backends = [
        DjangoFilterBackend,
        OrderingFilter,
    ]
    filterset_fields = ["action", "entity_type", "entity_id"]

    ordering_fields = [
        "occurred_at",
        "action",
        "entity_type",
    ]

    ordering = [
        "-occurred_at",
    ]
