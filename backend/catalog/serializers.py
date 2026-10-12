import re

import pycountry
from rest_framework import serializers

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    """Valida y serializa productos y servicios."""

    tenant = serializers.UUIDField(read_only=True)

    class Meta:
        model = Product

        fields = [
            "id",
            "tenant",
            "sku",
            "name",
            "description",
            "product_type",
            "unit",
            "unit_price",
            "currency",
            "tax_rate",
            "is_active",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "tenant",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError("El nombre es obligatorio.")

        return value

    def validate_sku(self, value):
        if not value:
            return None

        value = value.strip().upper()

        if not value:
            return None

        if len(value) > 64:
            raise serializers.ValidationError("El SKU no puede superar los 64 caracteres.")

        tenant = getattr(
            self.context.get("request"),
            "tenant",
            None,
        )

        if tenant is not None:
            duplicates = Product.objects.filter(
                tenant=tenant,
                sku=value,
            )

            if self.instance is not None:
                duplicates = duplicates.exclude(
                    pk=self.instance.pk,
                )

            if duplicates.exists():
                raise serializers.ValidationError("Este SKU ya está registrado en la empresa.")

        return value

    def validate_currency(self, value):
        value = value.strip().upper()

        if not re.fullmatch(r"[A-Z]{3}", value) or pycountry.currencies.get(alpha_3=value) is None:
            raise serializers.ValidationError(
                "La moneda debe ser un código de tres letras, por ejemplo ARS o USD."
            )

        return value

    def validate_unit_price(self, value):
        if value < 0:
            raise serializers.ValidationError("El precio no puede ser negativo.")

        return value

    def validate_tax_rate(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("La tasa fiscal debe estar entre 0 y 100.")

        return value

    def validate(self, attrs):
        """
        Comprueba la moneda y los datos generales.
        La empresa siempre se asigna desde la vista autorizada.
        """
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None)

        if tenant is None:
            raise serializers.ValidationError("No se pudo determinar la empresa autorizada.")

        return attrs
