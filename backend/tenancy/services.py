"""Explicit, serialized operations for enterprise identity and permissions."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from auditlog.models import AuditEvent
from auditlog.services import record_audit_event

from .models import Membership, Tenant

MANAGERS = {Membership.Role.OWNER, Membership.Role.ADMIN}
LAST_OWNER_MESSAGE = (
    "La empresa debe conservar al menos un propietario con cuenta y membresía activas."
)


def lock_company(tenant_id, *, actor, roles=MANAGERS, platform=False):
    """Caller owns an atomic block. Lock any target account before the tenant."""
    tenant = Tenant.objects.select_for_update().filter(pk=tenant_id).first()
    if tenant is None:
        raise NotFound("La empresa no está disponible.")
    user = get_user_model().objects.filter(pk=actor.pk, is_active=True).first()
    if user is None:
        raise PermissionDenied("La cuenta no está disponible.")
    if platform:
        if not user.is_staff or not user.has_perm("tenancy.change_membership"):
            raise PermissionDenied("No tenés permisos de administración de plataforma.")
        return tenant, None
    membership = Membership.objects.filter(tenant=tenant, user=user, is_active=True).first()
    if not tenant.is_active or membership is None or membership.role not in roles:
        raise PermissionDenied("No tenés permisos para esta operación en la empresa.")
    return tenant, membership


def check_last_owner(member, *, role, is_active):
    if member.is_active and member.role == Membership.Role.OWNER:
        removing = not is_active or role != Membership.Role.OWNER
        if (
            removing
            and not Membership.objects.filter(
                tenant_id=member.tenant_id,
                role=Membership.Role.OWNER,
                is_active=True,
                user__is_active=True,
            )
            .exclude(pk=member.pk)
            .exists()
        ):
            raise ValidationError({"is_active": LAST_OWNER_MESSAGE})


@transaction.atomic
def change_member(
    *, tenant_id, member_id, actor, role=None, is_active=None, request=None, platform=False
):
    member = Membership.objects.filter(pk=member_id, tenant_id=tenant_id).first()
    if member is None:
        raise NotFound("La membresía no está disponible.")
    target_user = get_user_model().objects.select_for_update(no_key=True).get(pk=member.user_id)
    tenant, manager = lock_company(tenant_id, actor=actor, platform=platform)
    member = Membership.objects.select_for_update().get(pk=member.pk)
    role = member.role if role is None else role
    is_active = member.is_active if is_active is None else is_active
    if role not in Membership.Role.values or not isinstance(is_active, bool):
        raise ValidationError("El rol o el estado no es válido.")
    if manager and manager.role == Membership.Role.ADMIN:
        if member.role in MANAGERS or role in MANAGERS:
            raise PermissionDenied(
                "Solo un propietario puede administrar propietarios y administradores."
            )
    if is_active and not target_user.is_active:
        raise ValidationError({"is_active": "La cuenta del usuario está desactivada."})
    check_last_owner(member, role=role, is_active=is_active)
    before = {"role": member.role, "is_active": member.is_active}
    after = {"role": role, "is_active": is_active}
    if before != after:
        member.role, member.is_active = role, is_active
        member.save(update_fields=["role", "is_active", "updated_at"])
        record_audit_event(
            action=AuditEvent.Action.UPDATE if is_active else AuditEvent.Action.DEACTIVATE,
            entity_type="tenancy.membership",
            entity_id=str(member.pk),
            tenant=tenant,
            actor=actor,
            request=request,
            changes={
                "fields": {
                    k: {"before": before[k], "after": after[k]}
                    for k in before
                    if before[k] != after[k]
                }
            },
        )
    return member


def guard_user_deactivation(user_id):
    """Admin form runs inside Django's change-form transaction; locks survive validation."""
    user = get_user_model().objects.select_for_update(no_key=True).get(pk=user_id)
    if not user.is_active:
        return
    tenant_ids = list(
        Membership.objects.filter(user_id=user_id).values_list("tenant_id", flat=True)
    )
    list(Tenant.objects.select_for_update().filter(pk__in=tenant_ids).order_by("pk"))
    owned = Membership.objects.filter(user_id=user_id, role="owner", is_active=True)
    for member in owned:
        try:
            check_last_owner(member, role=member.role, is_active=False)
        except ValidationError as exc:
            raise ModelValidationError(LAST_OWNER_MESSAGE) from exc


def settings_data(tenant):
    from .models import BusinessSettings

    settings = BusinessSettings.objects.filter(tenant=tenant).first() or BusinessSettings(
        tenant=tenant
    )
    fields = (
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
        "logo_updated_at",
    )
    return {
        "name": tenant.name,
        "legal_name": tenant.legal_name,
        "tax_id": tenant.tax_id,
        "has_logo": bool(settings.logo),
        **{k: getattr(settings, k) for k in fields},
    }


@transaction.atomic
def update_business_settings(*, tenant_id, actor, data, request=None):
    from django.utils import timezone

    from .models import BusinessSettings

    tenant, _ = lock_company(tenant_id, actor=actor)
    settings, _ = BusinessSettings.objects.get_or_create(tenant=tenant)
    before = settings_data(tenant)
    for field in ("name", "legal_name", "tax_id"):
        if field in data:
            setattr(tenant, field, data[field])
    tenant.save(update_fields=["name", "legal_name", "tax_id", "updated_at"])
    for field in before.keys() - {"name", "legal_name", "tax_id", "has_logo", "logo_updated_at"}:
        if field in data:
            setattr(settings, field, data[field])
    logo_changed = "logo_data" in data or data.get("remove_logo", False)
    if logo_changed:
        settings.logo = data.get("logo_data")
        settings.logo_updated_at = timezone.now()
    settings.save()
    after = settings_data(tenant)
    changes = {
        k: {
            "before": str(before[k]) if before[k] is not None else None,
            "after": str(after[k]) if after[k] is not None else None,
        }
        for k in before
        if before[k] != after[k]
    }
    if changes or logo_changed:
        record_audit_event(
            action=AuditEvent.Action.UPDATE,
            entity_type="tenancy.settings",
            entity_id=str(tenant.pk),
            tenant=tenant,
            actor=actor,
            request=request,
            changes={"fields": changes},
            metadata={"logo_changed": logo_changed},
        )
    return after
