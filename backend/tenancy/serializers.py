from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pycountry
from rest_framework import serializers

from .models import BusinessSettings, Membership, TenantInvitation


class StrictInputMixin:
    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError(
                {"non_field_errors": ["La solicitud contiene campos no admitidos."]}
            )
        return super().to_internal_value(data)


class BusinessSettingsSerializer(StrictInputMixin, serializers.ModelSerializer):
    name = serializers.CharField(max_length=150)
    legal_name = serializers.CharField(max_length=200, allow_blank=True, required=False)
    tax_id = serializers.CharField(max_length=20, allow_blank=True, required=False)
    has_logo = serializers.BooleanField(read_only=True)
    logo_data = serializers.CharField(write_only=True, required=False, max_length=700000)
    remove_logo = serializers.BooleanField(write_only=True, required=False)
    payment_terms_days = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=3650
    )

    class Meta:
        model = BusinessSettings
        fields = [
            "name",
            "legal_name",
            "tax_id",
            "country_code",
            "timezone",
            "default_currency",
            "contact_email",
            "contact_phone",
            "address",
            "website",
            "payment_terms_days",
            "invoice_footer",
            "payment_reminders_enabled",
            "has_logo",
            "logo_updated_at",
            "logo_data",
            "remove_logo",
        ]
        read_only_fields = ["logo_updated_at"]

    def validate_country_code(self, value):
        value = value.upper()
        if pycountry.countries.get(alpha_2=value) is None:
            raise serializers.ValidationError("Seleccioná un país ISO válido.")
        return value

    def validate_default_currency(self, value):
        value = value.upper()
        if pycountry.currencies.get(alpha_3=value) is None:
            raise serializers.ValidationError("Seleccioná una moneda ISO válida.")
        return value

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError("Introducí una zona horaria IANA válida.")
        return value

    def validate_logo_data(self, value):
        from .images import decode_private_image

        return decode_private_image(value)

    def validate(self, attrs):
        if attrs.get("remove_logo") and "logo_data" in attrs:
            raise serializers.ValidationError("Elegí subir o quitar el logo, no ambas acciones.")
        return attrs


class MembershipReadSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    user_active = serializers.BooleanField(source="user.is_active", read_only=True)

    class Meta:
        model = Membership
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "user_active",
            "created_at",
        ]


class MembershipUpdateSerializer(StrictInputMixin, serializers.Serializer):
    role = serializers.ChoiceField(choices=Membership.Role.choices, required=False)
    is_active = serializers.BooleanField(required=False)


class InvitationCreateSerializer(StrictInputMixin, serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    role = serializers.ChoiceField(choices=Membership.Role.choices)

    def validate_email(self, value):
        return value.strip().lower()


class InvitationReadSerializer(serializers.ModelSerializer):
    state = serializers.SerializerMethodField()

    def get_state(self, instance) -> str:
        from django.utils import timezone

        return (
            "expired"
            if instance.status == "pending" and instance.expires_at <= timezone.now()
            else instance.status
        )

    class Meta:
        model = TenantInvitation
        fields = [
            "id",
            "email",
            "role",
            "state",
            "delivery_status",
            "expires_at",
            "sent_at",
            "created_at",
        ]


class InvitationTokenSerializer(StrictInputMixin, serializers.Serializer):
    token = serializers.CharField(min_length=40, max_length=128)


class InvitationAcceptSerializer(InvitationTokenSerializer):
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, max_length=128, required=False)
    password_confirm = serializers.CharField(write_only=True, max_length=128, required=False)
