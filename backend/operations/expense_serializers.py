from decimal import Decimal

import pycountry
from rest_framework import serializers

from tenancy.images import decode_private_image
from tenancy.serializers import StrictInputMixin

from .models import Expense, ExpenseCategory, ExpensePayment


class CategorySerializer(StrictInputMixin, serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ["id", "name", "is_active"]
        read_only_fields = ["id"]
        validators = []


class ExpenseInput(StrictInputMixin, serializers.Serializer):
    purchase_order = serializers.UUIDField(required=False, allow_null=True)
    supplier = serializers.UUIDField(required=False, allow_null=True)
    category = serializers.UUIDField(required=False, allow_null=True)
    description = serializers.CharField(max_length=1000)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    incurred_on = serializers.DateField()
    due_date = serializers.DateField(required=False, allow_null=True)
    currency = serializers.CharField(min_length=3, max_length=3)
    net_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01")
    )
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False
    )
    attachment_data = serializers.CharField(max_length=700000, required=False)
    remove_attachment = serializers.BooleanField(required=False)

    def validate_currency(self, value):
        value = value.upper()
        if pycountry.currencies.get(alpha_3=value) is None:
            raise serializers.ValidationError("Elegí una moneda ISO válida.")
        return value

    def validate_attachment_data(self, value):
        return decode_private_image(value, thumbnail=(1600, 1600), max_output=2 * 1024 * 1024)

    def validate(self, attrs):
        if attrs.get("remove_attachment") and "attachment_data" in attrs:
            raise serializers.ValidationError("Elegí subir o quitar el adjunto.")
        return attrs


class ExpenseReadSerializer(serializers.ModelSerializer):
    paid_amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    balance = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    has_attachment = serializers.BooleanField(read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default="")
    category_name = serializers.CharField(source="category.name", read_only=True, default="")

    class Meta:
        model = Expense
        fields = [
            "id",
            "purchase_order",
            "supplier",
            "category",
            "supplier_name",
            "category_name",
            "supplier_name_snapshot",
            "category_name_snapshot",
            "description",
            "reference",
            "incurred_on",
            "due_date",
            "currency",
            "net_amount",
            "tax_rate",
            "tax_amount",
            "total",
            "status",
            "paid_amount",
            "balance",
            "has_attachment",
            "posted_at",
            "posted_by",
            "void_reason",
            "created_by",
            "created_at",
            "updated_at",
        ]


class ExpensePaymentInput(StrictInputMixin, serializers.Serializer):
    amount = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal("0.01"))
    method = serializers.ChoiceField(choices=ExpensePayment.Method.choices)
    reference = serializers.CharField(max_length=120, allow_blank=True, default="")
    paid_at = serializers.DateTimeField(required=False)


class ExpensePaymentSerializer(serializers.ModelSerializer):
    reversed_at = serializers.DateTimeField(
        source="reversal.occurred_at", read_only=True, default=None
    )
    reversal_reason = serializers.CharField(source="reversal.reason", read_only=True, default="")

    class Meta:
        model = ExpensePayment
        fields = [
            "id",
            "expense",
            "amount",
            "method",
            "reference",
            "paid_at",
            "actor",
            "created_at",
            "reversed_at",
            "reversal_reason",
        ]
