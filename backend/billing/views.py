from decimal import Decimal

from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from tenancy.mixins import TenantQuerySetMixin
from tenancy.models import Membership
from tenancy.permissions import TenantAccessPermission

from .filters import PaymentFilter
from .models import Invoice, Payment
from .serializers import (
    InvoiceDraftCreateSerializer,
    InvoiceReadSerializer,
    PaymentCreateSerializer,
    PaymentReadSerializer,
    PaymentReversalCreateSerializer,
    PaymentReversalReadSerializer,
)
from .services import (
    create_invoice_draft,
    issue_invoice,
    record_payment,
    reverse_payment,
)


class InvoiceViewSet(
    TenantQuerySetMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    API de facturación interna.

    Permite listar, crear borradores, consultar y emitir
    facturas dentro de la empresa autorizada.

    No permite modificar ni eliminar documentos mediante
    los endpoints genéricos.
    """

    queryset = (
        Invoice.objects.select_related(
            "tenant",
            "customer",
            "created_by",
            "issued_by",
        )
        .prefetch_related("lines")
        .annotate(
            paid_amount=Coalesce(
                Sum(
                    "payments__amount",
                    filter=Q(payments__reversal__isnull=True, payments__tenant_id=F("tenant_id")),
                ),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            )
        )
        .all()
    )

    permission_classes = [
        TenantAccessPermission,
    ]

    http_method_names = [
        "get",
        "post",
        "head",
        "options",
    ]

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]
    search_fields = [
        "customer_name_snapshot",
        "customer_document_number_snapshot",
        "internal_number",
    ]

    filterset_fields = [
        "status",
        "document_kind",
        "currency",
    ]

    ordering_fields = [
        "created_at",
        "issued_at",
        "total",
        "internal_number",
    ]

    ordering = [
        "-created_at",
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, "swagger_fake_view", False):
            return queryset
        from .receivables import business_today, filter_receivables

        if not hasattr(self, "_business_today"):
            self._business_today = business_today(self.request.tenant.pk)
        return filter_receivables(queryset, self.request.query_params, self._business_today)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, "swagger_fake_view", False) and hasattr(self.request, "tenant"):
            from .receivables import business_today

            if not hasattr(self, "_business_today"):
                self._business_today = business_today(self.request.tenant.pk)
            context["business_today"] = self._business_today
        return context

    def get_serializer_class(self):
        if self.action == "create":
            return InvoiceDraftCreateSerializer

        return InvoiceReadSerializer

    @extend_schema(request=InvoiceDraftCreateSerializer, responses={201: InvoiceReadSerializer})
    def create(self, request, *args, **kwargs):
        """
        Valida la entrada y delega la creación al servicio
        transaccional. Los importes se calculan en el backend.
        """

        serializer = self.get_serializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        invoice = create_invoice_draft(
            tenant=self.get_authorized_tenant(),
            customer_id=data["customer"],
            currency=data["currency"],
            lines=data["lines"],
            actor=request.user,
            notes=data.get("notes", ""),
            request=request,
            **{k: data[k] for k in ("due_date", "payment_terms_days") if k in data},
        )

        output = InvoiceReadSerializer(
            invoice,
            context=self.get_serializer_context(),
        )

        return Response(
            output.data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=None, responses=InvoiceReadSerializer)
    @action(
        detail=True,
        methods=["post"],
        url_path="issue",
    )
    def issue(self, request, *args, **kwargs):
        """
        Emite una factura interna mediante el servicio
        que comprueba permisos, consistencia y numeración.
        """

        # get_object() utiliza el queryset filtrado por tenant.
        invoice = self.get_object()

        issued_invoice = issue_invoice(
            tenant=self.get_authorized_tenant(),
            invoice_id=invoice.pk,
            actor=request.user,
            request=request,
        )

        output = InvoiceReadSerializer(
            issued_invoice,
            context=self.get_serializer_context(),
        )

        return Response(
            output.data,
            status=status.HTTP_200_OK,
        )


class PaymentViewSet(
    TenantQuerySetMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    API para consultar pagos, registrar cobros y revertirlos.

    Todos los registros se limitan a la empresa autorizada.
    """

    queryset = (
        Payment.objects.select_related(
            "tenant",
            "invoice",
            "recorded_by",
        )
        .prefetch_related("reversal")
        .all()
    )

    serializer_class = PaymentReadSerializer

    permission_classes = [
        TenantAccessPermission,
    ]

    http_method_names = [
        "get",
        "post",
        "head",
        "options",
    ]

    # Excepciones explícitas a la política general:
    # los contadores pueden registrar pagos, pero no revertirlos.
    tenant_roles_by_action = {
        "create": frozenset(
            {
                Membership.Role.OWNER,
                Membership.Role.ADMIN,
                Membership.Role.ACCOUNTANT,
            }
        ),
        "reverse": frozenset(
            {
                Membership.Role.OWNER,
                Membership.Role.ADMIN,
            }
        ),
    }

    filter_backends = [
        DjangoFilterBackend,
        OrderingFilter,
    ]

    filterset_class = PaymentFilter

    ordering_fields = [
        "received_at",
        "created_at",
        "amount",
    ]

    ordering = ["-received_at", "-pk"]

    def get_serializer_class(self):
        if self.action == "create":
            return PaymentCreateSerializer

        if self.action == "reverse":
            return PaymentReversalCreateSerializer

        return PaymentReadSerializer

    @extend_schema(
        request=PaymentCreateSerializer,
        responses={201: PaymentReadSerializer},
        parameters=[
            OpenApiParameter(
                name="Idempotency-Key",
                location=OpenApiParameter.HEADER,
                type=str,
                required=False,
                description="8 a 128 caracteres alfanuméricos, guion o guion bajo. Reutilizar solo para el mismo contenido dentro de la empresa. Otro contenido responde 409.",
            ),
            OpenApiParameter(
                name="Idempotent-Replayed",
                location=OpenApiParameter.HEADER,
                type=bool,
                response=[201],
                description="Indica que se recuperó el cobro original sin registrar otro efecto.",
            ),
        ],
    )
    def create(self, request, *args, **kwargs):
        """Registra un pago mediante el servicio transaccional."""

        serializer = self.get_serializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payment = record_payment(
            tenant=self.get_authorized_tenant(),
            invoice_id=data["invoice"],
            actor=request.user,
            method=data["method"],
            amount=data["amount"],
            external_reference=data.get("external_reference"),
            received_at=data.get("received_at"),
            notes=data.get("notes", ""),
            request=request,
            idempotency_key=request.headers.get("Idempotency-Key"),
        )

        output = PaymentReadSerializer(
            payment,
            context=self.get_serializer_context(),
        )

        return Response(
            output.data,
            status=status.HTTP_201_CREATED,
            headers={
                "Idempotent-Replayed": "true"
                if getattr(payment, "_idempotent_replay", False)
                else "false"
            },
        )

    @extend_schema(
        request=PaymentReversalCreateSerializer, responses={201: PaymentReversalReadSerializer}
    )
    @action(detail=True, methods=["post"], url_path="reverse")
    def reverse(self, request, *args, **kwargs):
        """Revierte un pago sin eliminar el registro original."""

        # El queryset ya está filtrado por la empresa autorizada.
        payment = self.get_object()

        serializer = self.get_serializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        reversal = reverse_payment(
            tenant=self.get_authorized_tenant(),
            payment_id=payment.pk,
            actor=request.user,
            reason=serializer.validated_data["reason"],
            request=request,
        )

        output = PaymentReversalReadSerializer(
            reversal,
            context=self.get_serializer_context(),
        )

        return Response(
            output.data,
            status=status.HTTP_201_CREATED,
        )
