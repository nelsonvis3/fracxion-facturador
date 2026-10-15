from decimal import Decimal

from django.db.models import (
    BooleanField,
    Case,
    DecimalField,
    F,
    OuterRef,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from catalog.models import Product
from tenancy.mixins import TenantQuerySetMixin
from tenancy.permissions import TenantAccessPermission

from .filters import MovementFilter
from .models import InventoryMovement, Supplier
from .serializers import (
    InventoryInput,
    InventoryItemSerializer,
    InventoryMovementSerializer,
    InventoryPolicyInput,
    ReversalInput,
    SupplierSerializer,
)
from .services import move_stock, save_supplier, set_inventory_policy


class SupplierViewSet(
    TenantQuerySetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [TenantAccessPermission]
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["is_active", "country_code"]
    search_fields = ["name", "legal_name", "tax_id", "email"]

    def create(self, request, *args, **kwargs):
        result = save_supplier(
            tenant_id=request.tenant.pk, actor=request.user, data=request.data, request=request
        )
        return Response(self.get_serializer(result).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        result = save_supplier(
            tenant_id=request.tenant.pk,
            actor=request.user,
            supplier_id=self.get_object().pk,
            data=request.data,
            request=request,
        )
        return Response(self.get_serializer(result).data)


class InventoryItemViewSet(
    TenantQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [TenantAccessPermission]
    queryset = Product.objects.all()
    serializer_class = InventoryItemSerializer
    filter_backends = [SearchFilter]
    search_fields = ["name", "sku"]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        query = super().get_queryset().filter(product_type="product")
        if getattr(self, "swagger_fake_view", False):
            return query
        amount = DecimalField(max_digits=12, decimal_places=3)
        balances = (
            InventoryMovement.objects.filter(tenant=self.request.tenant, product=OuterRef("pk"))
            .order_by()
            .values("product")
            .annotate(total=Sum("delta"))
            .values("total")
        )
        query = query.annotate(
            balance=Coalesce(
                Subquery(balances, output_field=amount),
                Value(Decimal("0.000")),
                output_field=amount,
            ),
            minimum=Coalesce(
                "inventory_policy__minimum", Value(Decimal("0.000")), output_field=amount
            ),
            tracking=Coalesce("inventory_policy__tracking", Value(False)),
        ).annotate(
            low_stock=Case(
                When(tracking=True, balance__lte=F("minimum"), then=True),
                default=False,
                output_field=BooleanField(),
            )
        )
        low = self.request.query_params.get("low_stock")
        if low not in {None, "true", "false"}:
            raise serializers.ValidationError({"low_stock": "Usá true o false."})
        if low:
            query = query.filter(low_stock=low == "true")
        return query.order_by("name", "pk")

    @extend_schema(request=InventoryPolicyInput, responses=InventoryItemSerializer)
    def partial_update(self, request, *args, **kwargs):
        product = self.get_object()
        set_inventory_policy(
            tenant_id=request.tenant.pk,
            actor=request.user,
            product_id=product.pk,
            data=request.data,
            request=request,
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=product.pk)).data)


class InventoryMovementViewSet(
    TenantQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [TenantAccessPermission]
    queryset = InventoryMovement.objects.select_related("reversed_by")
    serializer_class = InventoryMovementSerializer
    http_method_names = ["get", "post", "head", "options"]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = MovementFilter
    search_fields = ["product_name_snapshot", "reference", "reason"]

    @extend_schema(
        request=InventoryInput,
        responses={201: InventoryMovementSerializer},
        parameters=[
            OpenApiParameter(
                name="Idempotency-Key", location=OpenApiParameter.HEADER, type=str, required=False
            )
        ],
    )
    def create(self, request, *args, **kwargs):
        movement = move_stock(
            tenant_id=request.tenant.pk,
            actor=request.user,
            data=request.data,
            idempotency_key=request.headers.get("Idempotency-Key"),
            request=request,
        )
        return Response(self.get_serializer(movement).data, status=201)

    @extend_schema(request=ReversalInput, responses={201: InventoryMovementSerializer})
    @action(detail=True, methods=["post"])
    def reverse(self, request, *args, **kwargs):
        original = self.get_object()
        movement = move_stock(
            tenant_id=request.tenant.pk,
            actor=request.user,
            data=request.data,
            idempotency_key=request.headers.get("Idempotency-Key"),
            reverse_id=original.pk,
            request=request,
        )
        return Response(self.get_serializer(movement).data, status=201)
