import pycountry
from rest_framework import serializers

from tenancy.serializers import StrictInputMixin

from .models import InventoryMovement, Supplier


class SupplierSerializer(StrictInputMixin, serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            "id",
            "name",
            "legal_name",
            "tax_id",
            "country_code",
            "email",
            "phone",
            "address",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_country_code(self, value):
        value = value.upper()
        if pycountry.countries.get(alpha_2=value) is None:
            raise serializers.ValidationError("País ISO no válido.")
        return value


class InventoryPolicyInput(StrictInputMixin, serializers.Serializer):
    tracking = serializers.BooleanField(required=False)
    minimum = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0, required=False)


class InventoryInput(StrictInputMixin, serializers.Serializer):
    product = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["in", "out", "adjustment"])
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    reason = serializers.CharField(max_length=500)
    reference = serializers.CharField(max_length=120, allow_blank=True, required=False, default="")


class ReversalInput(StrictInputMixin, serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class InventoryMovementSerializer(serializers.ModelSerializer):
    reversed_by = serializers.UUIDField(source="reversed_by.pk", read_only=True, default=None)

    class Meta:
        model = InventoryMovement
        fields = [
            "id",
            "product",
            "kind",
            "delta",
            "balance_after",
            "reason",
            "reference",
            "product_name_snapshot",
            "unit_snapshot",
            "actor",
            "reverses",
            "reversed_by",
            "occurred_at",
        ]


class InventoryItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    sku = serializers.CharField(allow_null=True)
    unit = serializers.CharField()
    is_active = serializers.BooleanField()
    balance = serializers.DecimalField(max_digits=12, decimal_places=3)
    minimum = serializers.DecimalField(max_digits=12, decimal_places=3)
    tracking = serializers.BooleanField()
    low_stock = serializers.BooleanField()
