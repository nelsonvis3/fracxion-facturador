from decimal import Decimal

from rest_framework import serializers

from tenancy.serializers import StrictInputMixin

from .expense_serializers import ExpenseInput
from .models import PurchaseLine, PurchaseOrder, PurchaseReceipt, PurchaseReceiptLine


class PurchaseLineInput(StrictInputMixin, serializers.Serializer):
    product = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)


class PurchaseInput(StrictInputMixin, serializers.Serializer):
    supplier = serializers.UUIDField()
    currency = serializers.CharField(min_length=3, max_length=3)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    expected_on = serializers.DateField(required=False, allow_null=True)
    lines = PurchaseLineInput(many=True, min_length=1, max_length=100)

    def validate_currency(self, value):
        return ExpenseInput().validate_currency(value)


class ReceiptLineInput(StrictInputMixin, serializers.Serializer):
    line = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))


class ReceiptInput(StrictInputMixin, serializers.Serializer):
    reference = serializers.CharField(max_length=120, required=False, default="", allow_blank=True)
    lines = ReceiptLineInput(many=True, min_length=1, max_length=100)


class PurchaseLineRead(serializers.ModelSerializer):
    received_quantity = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    remaining_quantity = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)

    class Meta:
        model = PurchaseLine
        fields = [
            "id",
            "product",
            "position",
            "product_name_snapshot",
            "product_type_snapshot",
            "unit_snapshot",
            "quantity",
            "unit_cost",
            "tax_rate",
            "net_amount",
            "tax_amount",
            "total",
            "received_quantity",
            "remaining_quantity",
        ]


class PurchaseRead(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "supplier",
            "supplier_name",
            "supplier_name_snapshot",
            "reference",
            "notes",
            "currency",
            "expected_on",
            "status",
            "net_amount",
            "tax_amount",
            "total",
            "created_by",
            "confirmed_at",
            "closed_at",
            "close_reason",
            "created_at",
            "updated_at",
        ]


class ReceiptLineRead(serializers.ModelSerializer):
    class Meta:
        model = PurchaseReceiptLine
        fields = ["id", "line", "quantity", "movement"]


class ReceiptRead(serializers.ModelSerializer):
    lines = ReceiptLineRead(many=True, read_only=True)
    reversal = serializers.UUIDField(source="reversal.pk", default=None, read_only=True)
    reversal_reason = serializers.CharField(source="reversal.reason", default="", read_only=True)

    class Meta:
        model = PurchaseReceipt
        fields = [
            "id",
            "order",
            "reference",
            "actor",
            "occurred_at",
            "lines",
            "reversal",
            "reversal_reason",
        ]
