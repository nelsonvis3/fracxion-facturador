from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from auditlog.models import AuditEvent
from auditlog.services import record_audit_event
from tenancy.mixins import TenantMutationMixin
from tenancy.permissions import TenantAccessPermission

from .models import Customer
from .serializers import CustomerSerializer

AUDITED_FIELDS = (
    "customer_type",
    "name",
    "legal_name",
    "document_type",
    "document_number",
    "email",
    "phone",
    "address",
    "city",
    "province",
    "postal_code",
    "country_code",
    "is_active",
)


def customer_audit_snapshot(customer):
    """
    Devuelve únicamente campos estructurados para la auditoría.
    No copia el campo libre 'notes', que podría contener secretos
    u otra información innecesaria.
    """
    return {field: getattr(customer, field) for field in AUDITED_FIELDS}


def customer_audit_changes(before, after):
    """Devuelve exclusivamente los campos que cambiaron."""
    return {
        field: {
            "before": before[field],
            "after": after[field],
        }
        for field in AUDITED_FIELDS
        if before[field] != after[field]
    }


class CustomerViewSet(
    TenantMutationMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """API de clientes protegida por empresa y membresía."""

    queryset = Customer.objects.select_related(
        "tenant",
        "created_by",
    ).all()

    serializer_class = CustomerSerializer

    permission_classes = [
        TenantAccessPermission,
    ]

    http_method_names = [
        "get",
        "post",
        "put",
        "patch",
        "head",
        "options",
    ]

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = [
        "customer_type",
        "document_type",
        "is_active",
        "province",
    ]

    search_fields = [
        "name",
        "legal_name",
        "document_number",
        "email",
    ]

    ordering_fields = [
        "name",
        "created_at",
        "updated_at",
    ]

    ordering = ["name"]

    def perform_create(self, serializer):
        """Crea el cliente y su evento de auditoría atómicamente."""
        tenant = self.get_authorized_tenant()

        with transaction.atomic():
            customer = serializer.save(
                tenant=tenant,
                created_by=self.request.user,
            )

            metadata = {}

            if customer.notes:
                metadata["redacted_fields_present"] = ["notes"]

            record_audit_event(
                action=AuditEvent.Action.CREATE,
                entity_type="customers.customer",
                entity_id=str(customer.pk),
                tenant=tenant,
                actor=self.request.user,
                changes={
                    "fields": customer_audit_snapshot(customer),
                },
                metadata=metadata,
                request=self.request,
            )

    def perform_update(self, serializer):
        """Registra cambios sin guardar el contenido de notas."""
        tenant = self.get_authorized_tenant()

        with transaction.atomic():
            before_customer = serializer.instance
            before = customer_audit_snapshot(before_customer)
            previous_notes = before_customer.notes

            customer = serializer.save(tenant=tenant)

            after = customer_audit_snapshot(customer)
            changes = customer_audit_changes(before, after)
            metadata = {}

            if previous_notes != customer.notes:
                metadata["redacted_fields_changed"] = ["notes"]

            # No generamos eventos vacíos cuando no cambió ningún dato.
            if changes or metadata:
                record_audit_event(
                    action=AuditEvent.Action.UPDATE,
                    entity_type="customers.customer",
                    entity_id=str(customer.pk),
                    tenant=tenant,
                    actor=self.request.user,
                    changes={"fields": changes},
                    metadata=metadata,
                    request=self.request,
                )

    @action(
        detail=True,
        methods=["post"],
        url_path="deactivate",
    )
    def deactivate(self, request, *args, **kwargs):
        """Desactiva un cliente conservando su historial."""
        tenant = self.get_authorized_tenant()
        customer = self.get_object()

        with transaction.atomic():
            try:
                customer = Customer.objects.select_for_update().get(
                    pk=customer.pk,
                    tenant=tenant,
                )
            except Customer.DoesNotExist:
                raise NotFound("El cliente no existe en esta empresa.")

            if customer.is_active:
                before = customer_audit_snapshot(customer)

                customer.is_active = False
                customer.save(
                    update_fields=["is_active", "updated_at"],
                )

                after = customer_audit_snapshot(customer)
                changes = customer_audit_changes(before, after)

                record_audit_event(
                    action=AuditEvent.Action.DEACTIVATE,
                    entity_type="customers.customer",
                    entity_id=str(customer.pk),
                    tenant=tenant,
                    actor=request.user,
                    changes={"fields": changes},
                    request=request,
                )

        return Response(
            self.get_serializer(customer).data,
            status=status.HTTP_200_OK,
        )
