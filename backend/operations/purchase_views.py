from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from tenancy.mixins import TenantQuerySetMixin
from tenancy.permissions import TenantAccessPermission

from .filters import PurchaseFilter
from .models import PurchaseOrder, PurchaseReceipt
from .purchase_serializers import (
    PurchaseInput,
    PurchaseLineRead,
    PurchaseRead,
    ReceiptInput,
    ReceiptRead,
)
from .purchases import (
    READ_ROLES,
    close_purchase,
    confirm_purchase,
    purchase_lines,
    receive_purchase,
    reverse_receipt,
    save_purchase,
)
from .serializers import ReversalInput


class PurchaseViewSet(
    TenantQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = PurchaseOrder.objects.select_related("supplier")
    serializer_class = PurchaseRead
    permission_classes = [TenantAccessPermission]
    tenant_roles_by_action = {key: READ_ROLES for key in ["list", "retrieve", "lines"]}
    http_method_names = ["get", "post", "patch", "head", "options"]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = PurchaseFilter
    search_fields = ["reference", "supplier_name_snapshot", "supplier__name"]

    @extend_schema(request=PurchaseInput, responses={201: PurchaseRead})
    def create(self, request, *args, **kwargs):
        order = save_purchase(
            tenant_id=request.tenant.pk, actor=request.user, data=request.data, request=request
        )
        return Response(self.get_serializer(order).data, status=201)

    @extend_schema(request=PurchaseInput, responses=PurchaseRead)
    def partial_update(self, request, *args, **kwargs):
        order = save_purchase(
            tenant_id=request.tenant.pk,
            actor=request.user,
            data=request.data,
            order_id=self.get_object().pk,
            request=request,
        )
        return Response(self.get_serializer(order).data)

    @extend_schema(request=None, responses=PurchaseRead)
    @action(detail=True, methods=["post"])
    def confirm(self, request, *args, **kwargs):
        order = confirm_purchase(
            tenant_id=request.tenant.pk,
            actor=request.user,
            order_id=self.get_object().pk,
            request=request,
        )
        return Response(self.get_serializer(order).data)

    @extend_schema(request=ReversalInput, responses=PurchaseRead)
    @action(detail=True, methods=["post"])
    def close(self, request, *args, **kwargs):
        order = close_purchase(
            tenant_id=request.tenant.pk,
            actor=request.user,
            order_id=self.get_object().pk,
            data=request.data,
            request=request,
        )
        return Response(self.get_serializer(order).data)

    @extend_schema(responses=PurchaseLineRead(many=True))
    @action(detail=True, methods=["get"])
    def lines(self, request, *args, **kwargs):
        # A purchase has at most 100 lines; unlike histories this collection is bounded.
        return Response(PurchaseLineRead(purchase_lines(self.get_object()), many=True).data)

    @extend_schema(methods=["GET"], responses=ReceiptRead(many=True))
    @extend_schema(
        methods=["POST"],
        request=ReceiptInput,
        responses={201: ReceiptRead},
        parameters=[
            OpenApiParameter(name="Idempotency-Key", location=OpenApiParameter.HEADER, type=str)
        ],
    )
    @action(detail=True, methods=["get", "post"])
    def receipts(self, request, *args, **kwargs):
        order = self.get_object()
        if request.method == "POST":
            receipt = receive_purchase(
                tenant_id=request.tenant.pk,
                actor=request.user,
                order_id=order.pk,
                data=request.data,
                idempotency_key=request.headers.get("Idempotency-Key"),
                request=request,
            )
            return Response(
                ReceiptRead(
                    PurchaseReceipt.objects.select_related("reversal")
                    .prefetch_related("lines")
                    .get(pk=receipt.pk)
                ).data,
                status=201,
            )
        query = (
            PurchaseReceipt.objects.filter(tenant=request.tenant, order=order)
            .select_related("reversal")
            .prefetch_related("lines")
        )
        # Read permission differs from receipt mutation permission.
        page = self.paginate_queryset(query)
        return self.get_paginated_response(ReceiptRead(page, many=True).data)

    def get_permissions(self):
        if self.action == "receipts":
            self.tenant_roles_by_action = {
                **self.tenant_roles_by_action,
                "receipts": READ_ROLES
                if self.request.method in {"GET", "HEAD"}
                else {"owner", "admin"},
            }
        return super().get_permissions()


class PurchaseReceiptViewSet(TenantQuerySetMixin, viewsets.GenericViewSet):
    queryset = PurchaseReceipt.objects.all()
    serializer_class = ReceiptRead
    permission_classes = [TenantAccessPermission]
    http_method_names = ["post", "options"]

    @extend_schema(request=ReversalInput, responses=ReceiptRead)
    @action(detail=True, methods=["post"])
    def reverse(self, request, *args, **kwargs):
        receipt = self.get_object()
        reverse_receipt(
            tenant_id=request.tenant.pk,
            actor=request.user,
            receipt_id=receipt.pk,
            data=request.data,
            request=request,
        )
        return Response(
            ReceiptRead(
                PurchaseReceipt.objects.select_related("reversal")
                .prefetch_related("lines")
                .get(pk=receipt.pk)
            ).data
        )
