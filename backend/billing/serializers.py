import re
from decimal import Decimal

import pycountry
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from catalog.models import Product
from customers.models import Customer

from .models import (
    Invoice,
    InvoiceLine,
    Payment,
    PaymentReversal,
)
from .services import get_invoice_balance


class InvoiceLineInputSerializer(serializers.Serializer):
    """Datos permitidos para cada línea al crear un borrador."""

    product = serializers.UUIDField()

    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )


class InvoiceDraftCreateSerializer(serializers.Serializer):
    """
    Valida los datos para crear un borrador de factura interna.

    El cliente y los productos deben pertenecer al tenant
    autorizado. Los precios e impuestos nunca los decide el cliente.
    """

    customer = serializers.UUIDField()

    currency = serializers.CharField(
        max_length=3,
    )

    notes = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    lines = InvoiceLineInputSerializer(
        many=True,
        allow_empty=False,
        max_length=100,
    )

    def validate_currency(self, value):
        value = value.strip().upper()

        if not re.fullmatch(r"[A-Z]{3}", value) or pycountry.currencies.get(alpha_3=value) is None:
            raise serializers.ValidationError(
                "La moneda debe ser un código de tres letras, por ejemplo ARS o USD."
            )

        return value

    def validate(self, attrs):
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None)

        if tenant is None:
            raise serializers.ValidationError("No se pudo determinar la empresa autorizada.")

        # No revelar si el cliente existe en otra empresa.
        customer = Customer.objects.filter(
            pk=attrs["customer"],
            tenant=tenant,
            is_active=True,
        ).first()

        if customer is None:
            raise serializers.ValidationError(
                {"customer": ("El cliente no existe o no está disponible en esta empresa.")}
            )

        lines = attrs["lines"]
        product_ids = {line["product"] for line in lines}

        products = Product.objects.filter(
            pk__in=product_ids,
            tenant=tenant,
            is_active=True,
        )

        products_by_id = {product.pk: product for product in products}

        # La comparación usa los UUID distintos; un mismo producto
        # podría aparecer en más de una línea.
        if len(products_by_id) != len(product_ids):
            raise serializers.ValidationError(
                {
                    "lines": (
                        "Uno o más productos no existen, están inactivos "
                        "o no pertenecen a esta empresa."
                    )
                }
            )

        currency = attrs["currency"]

        if any(product.currency != currency for product in products_by_id.values()):
            raise serializers.ValidationError(
                {
                    "currency": (
                        "La moneda de la factura debe coincidir con la de todos los productos."
                    )
                }
            )

        # Contexto validado para el servicio de negocio.
        attrs["validated_customer"] = customer
        attrs["validated_products"] = products_by_id

        return attrs


class InvoiceLineReadSerializer(serializers.ModelSerializer):
    """Representación de solo lectura de una línea histórica."""

    class Meta:
        model = InvoiceLine

        fields = [
            "id",
            "position",
            "product",
            "description_snapshot",
            "sku_snapshot",
            "unit_snapshot",
            "quantity",
            "unit_price",
            "tax_rate",
            "subtotal",
            "tax_amount",
            "total",
        ]

        read_only_fields = fields


class InvoiceReadSerializer(serializers.ModelSerializer):
    """Representación de solo lectura de un documento."""

    lines = InvoiceLineReadSerializer(
        many=True,
        read_only=True,
    )

    created_by = serializers.StringRelatedField(
        read_only=True,
    )

    issued_by = serializers.StringRelatedField(
        read_only=True,
    )
    balance = serializers.SerializerMethodField()
    paid_total = serializers.SerializerMethodField()

    def get_balance(self, instance) -> str:
        if not hasattr(instance, "_balance"):
            instance._balance = (
                instance.total - instance.paid_amount
                if hasattr(instance, "paid_amount")
                else get_invoice_balance(instance)
            )
        return str(instance._balance.quantize(Decimal("0.01")))

    def get_paid_total(self, instance) -> str:
        return str((instance.total - Decimal(self.get_balance(instance))).quantize(Decimal("0.01")))

    class Meta:
        model = Invoice

        fields = [
            "id",
            "tenant",
            "customer",
            "created_by",
            "issued_by",
            "document_kind",
            "status",
            "internal_number",
            "currency",
            "customer_name_snapshot",
            "customer_legal_name_snapshot",
            "customer_document_type_snapshot",
            "customer_document_number_snapshot",
            "customer_address_snapshot",
            "customer_city_snapshot",
            "customer_province_snapshot",
            "customer_email_snapshot",
            "customer_country_code_snapshot",
            "customer_postal_code_snapshot",
            "subtotal",
            "tax_total",
            "total",
            "paid_total",
            "balance",
            "notes",
            "issued_at",
            "created_at",
            "updated_at",
            "lines",
        ]

        read_only_fields = fields


class PaymentCreateSerializer(serializers.Serializer):
    """Datos permitidos para registrar un pago."""

    invoice = serializers.UUIDField()

    method = serializers.ChoiceField(
        choices=Payment.Method.choices,
    )

    amount = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    external_reference = serializers.CharField(
        max_length=120,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    received_at = serializers.DateTimeField(
        required=False,
    )

    notes = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    def validate_invoice(self, value):
        """
        Comprueba que la factura pertenezca a la empresa
        autorizada y ya esté emitida.

        El servicio volverá a validar la operación dentro
        de la transacción.
        """
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None)

        if tenant is None:
            raise serializers.ValidationError("No se pudo determinar la empresa autorizada.")

        invoice_exists = Invoice.objects.filter(
            pk=value,
            tenant=tenant,
            status=Invoice.Status.ISSUED,
        ).exists()

        if not invoice_exists:
            raise serializers.ValidationError(
                "La factura no existe en esta empresa o todavía no está emitida."
            )

        return value


class PaymentReversalCreateSerializer(serializers.Serializer):
    """Datos permitidos para solicitar una reversión."""

    reason = serializers.CharField(
        max_length=2000,
        allow_blank=False,
        trim_whitespace=True,
    )

    def validate_reason(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError("El motivo de la reversión es obligatorio.")

        return value


class PaymentReversalReadSerializer(serializers.ModelSerializer):
    """Representación de solo lectura de una reversión."""

    tenant = serializers.UUIDField(
        source="tenant_id",
        read_only=True,
    )

    payment = serializers.UUIDField(
        source="payment_id",
        read_only=True,
    )

    reversed_by = serializers.CharField(
        source="reversed_by.email",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = PaymentReversal

        fields = [
            "id",
            "tenant",
            "payment",
            "reversed_by",
            "reason",
            "occurred_at",
            "created_at",
        ]

        read_only_fields = fields


class PaymentReadSerializer(serializers.ModelSerializer):
    """Representación de solo lectura de un pago."""

    tenant = serializers.UUIDField(
        source="tenant_id",
        read_only=True,
    )

    invoice = serializers.UUIDField(
        source="invoice_id",
        read_only=True,
    )

    recorded_by = serializers.CharField(
        source="recorded_by.email",
        read_only=True,
        allow_null=True,
    )

    method_label = serializers.CharField(
        source="get_method_display",
        read_only=True,
    )
    currency = serializers.CharField(source="invoice.currency", read_only=True)
    invoice_number = serializers.IntegerField(source="invoice.internal_number", read_only=True)
    customer_name = serializers.CharField(source="invoice.customer_name_snapshot", read_only=True)

    reversal = serializers.SerializerMethodField()

    class Meta:
        model = Payment

        fields = [
            "id",
            "tenant",
            "invoice",
            "recorded_by",
            "method",
            "method_label",
            "currency",
            "invoice_number",
            "customer_name",
            "amount",
            "external_reference",
            "received_at",
            "notes",
            "created_at",
            "reversal",
        ]

        read_only_fields = fields

    @extend_schema_field(PaymentReversalReadSerializer(allow_null=True))
    def get_reversal(self, instance):
        try:
            reversal = instance.reversal
        except PaymentReversal.DoesNotExist:
            return None

        return PaymentReversalReadSerializer(
            reversal,
            context=self.context,
        ).data
