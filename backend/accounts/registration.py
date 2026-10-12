"""Alta pública de una cuenta y su propia empresa, sin aceptar roles del cliente."""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils.text import slugify
from rest_framework import serializers

from auditlog.models import AuditEvent
from auditlog.services import record_audit_event
from tenancy.models import Membership, Tenant

REGISTRATION_LIMIT = 10
DUPLICATE_EMAIL_MESSAGE = "Ese correo ya tiene una cuenta. Iniciá sesión o recuperá tu contraseña."


class RegistrationSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    company_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)
    password_confirm = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError(
                    {field: ["Este campo no está permitido."] for field in sorted(unknown)}
                )
        return super().to_internal_value(data)

    def validate_email(self, value):
        value = value.strip().lower()
        if get_user_model().objects.filter(email=value).exists():
            raise serializers.ValidationError(DUPLICATE_EMAIL_MESSAGE)
        return value

    def validate_password(self, value):
        if not value.strip():
            raise serializers.ValidationError("La contraseña no puede contener solo espacios.")
        return value

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": ["Las contraseñas no coinciden."]}
            )
        user = get_user_model()(
            email=data["email"], first_name=data["first_name"], last_name=data["last_name"]
        )
        try:
            validate_password(data["password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc
        return data


def register_account(*, data, request=None):
    """Valida la entrada y guarda cuenta, empresa, membresía y auditoría juntas."""
    serializer = RegistrationSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    fields = serializer.validated_data
    try:
        with transaction.atomic():
            user = get_user_model().objects.create_user(
                email=fields["email"],
                password=fields["password"],
                first_name=fields["first_name"],
                last_name=fields["last_name"],
            )
            tenant = Tenant(name=fields["company_name"])
            # El UUID evita colisiones incluso si dos empresas comparten nombre.
            prefix = slugify(tenant.name)[:60] or "empresa"
            tenant.slug = f"{prefix}-{tenant.pk.hex}"
            tenant.save(force_insert=True)
            Membership.objects.create(tenant=tenant, user=user, role=Membership.Role.OWNER)
            record_audit_event(
                action=AuditEvent.Action.CREATE,
                entity_type="tenancy.tenant",
                entity_id=str(tenant.pk),
                tenant=tenant,
                actor=user,
                changes={"fields": {"name": {"before": None, "after": tenant.name}}},
                metadata={"source": "registration"},
                request=request,
            )
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", "")
        if constraint == "accounts_user_email_key":
            raise serializers.ValidationError({"email": [DUPLICATE_EMAIL_MESSAGE]}) from exc
        raise
    return user, tenant
