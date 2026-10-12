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

from .models import Product
from .serializers import ProductSerializer

AUDITED_FIELDS = (
    "name",
    "sku",
    "product_type",
    "unit",
    "unit_price",
    "currency",
    "tax_rate",
    "is_active",
)


def product_audit_snapshot(product):
    """
    Genera una representación segura del producto.
    Los importes se convierten a texto para JSONField.
    No registra el contenido libre de description.
    """
    snapshot = {field: getattr(product, field) for field in AUDITED_FIELDS}

    snapshot["unit_price"] = str(product.unit_price)
    snapshot["tax_rate"] = str(product.tax_rate)

    return snapshot


def product_audit_changes(before, after):
    """Devuelve solo los campos cuyo valor cambió."""
    return {
        field: {
            "before": before[field],
            "after": after[field],
        }
        for field in AUDITED_FIELDS
        if before[field] != after[field]
    }


class ProductViewSet(
    TenantMutationMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    API de productos y servicios con aislamiento multi-tenant
    y auditoría transaccional.
    """

    queryset = Product.objects.select_related(
        "tenant",
    ).all()

    serializer_class = ProductSerializer

    permission_classes = [
        TenantAccessPermission,
    ]

    # No ofrecemos eliminación física de productos.
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
        "product_type",
        "unit",
        "currency",
        "is_active",
    ]

    search_fields = [
        "name",
        "sku",
        "description",
    ]

    ordering_fields = [
        "name",
        "unit_price",
        "created_at",
        "updated_at",
    ]

    ordering = ["name"]

    def perform_create(self, serializer):
        """Crea el producto y su auditoría en una transacción."""
        tenant = self.get_authorized_tenant()

        with transaction.atomic():
            product = serializer.save(tenant=tenant)

            metadata = {}

            if product.description:
                metadata["redacted_fields_present"] = [
                    "description",
                ]

            record_audit_event(
                action=AuditEvent.Action.CREATE,
                entity_type="catalog.product",
                entity_id=str(product.pk),
                tenant=tenant,
                actor=self.request.user,
                changes={
                    "fields": product_audit_snapshot(product),
                },
                metadata=metadata,
                request=self.request,
            )

    def perform_update(self, serializer):
        """Registra los cambios del producto sin copiar su descripción."""
        tenant = self.get_authorized_tenant()

        with transaction.atomic():
            previous_product = serializer.instance
            before = product_audit_snapshot(previous_product)
            previous_description = previous_product.description

            product = serializer.save(tenant=tenant)

            after = product_audit_snapshot(product)
            changes = product_audit_changes(before, after)
            metadata = {}

            if previous_description != product.description:
                metadata["redacted_fields_changed"] = [
                    "description",
                ]

            if changes or metadata:
                record_audit_event(
                    action=AuditEvent.Action.UPDATE,
                    entity_type="catalog.product",
                    entity_id=str(product.pk),
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
        """Desactiva un producto sin eliminar su historial."""
        tenant = self.get_authorized_tenant()
        product = self.get_object()

        with transaction.atomic():
            try:
                product = Product.objects.select_for_update().get(
                    pk=product.pk,
                    tenant=tenant,
                )
            except Product.DoesNotExist:
                raise NotFound("El producto no existe en esta empresa.")

            if product.is_active:
                before = product_audit_snapshot(product)

                product.is_active = False
                product.save(
                    update_fields=["is_active", "updated_at"],
                )

                after = product_audit_snapshot(product)
                changes = product_audit_changes(before, after)

                record_audit_event(
                    action=AuditEvent.Action.DEACTIVATE,
                    entity_type="catalog.product",
                    entity_id=str(product.pk),
                    tenant=tenant,
                    actor=request.user,
                    changes={"fields": changes},
                    request=request,
                )

        return Response(
            self.get_serializer(product).data,
            status=status.HTTP_200_OK,
        )
