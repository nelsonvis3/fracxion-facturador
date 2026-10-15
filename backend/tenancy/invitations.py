"""Secure company invitations; raw tokens exist only in the outgoing email."""

import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as PasswordValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from auditlog.models import AuditEvent
from auditlog.services import record_audit_event

from .models import Membership, Tenant, TenantInvitation
from .services import MANAGERS, lock_company

logger = logging.getLogger(__name__)
INVALID_INVITATION = "La invitación no es válida, fue revocada o ha vencido."


def token_digest(token):
    if not isinstance(token, str) or not 40 <= len(token) <= 128:
        raise ValidationError({"token": INVALID_INVITATION})
    return hashlib.sha256(token.encode()).hexdigest()


def authorize_role(manager, role):
    if role not in Membership.Role.values:
        raise ValidationError({"role": "Seleccioná un rol válido."})
    if manager.role != Membership.Role.OWNER and role in MANAGERS:
        raise PermissionDenied("Solo un propietario puede invitar administradores o propietarios.")


def deliver_invitation(invitation_id, token):
    invitation = TenantInvitation.objects.select_related("tenant").get(pk=invitation_id)
    if invitation.status != "pending" or invitation.token_digest != token_digest(token):
        return
    url = urlsplit(settings.FRONTEND_PASSWORD_RESET_URL)
    link = urlunsplit((url.scheme, url.netloc, "/accept-invitation", "", "token=" + token))
    try:
        send_mail(
            subject=f"Invitación a {invitation.tenant.name}",
            message=f"Te invitaron a trabajar en {invitation.tenant.name} con el rol {invitation.get_role_display()}.\n\n{link}\n\nLa invitación vence en siete días. Si no la esperabas, podés ignorarla.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            fail_silently=False,
        )
        TenantInvitation.objects.filter(pk=invitation.pk, token_digest=token_digest(token)).update(
            delivery_status="sent", sent_at=timezone.now()
        )
    except Exception:
        TenantInvitation.objects.filter(pk=invitation.pk, token_digest=token_digest(token)).update(
            delivery_status="failed"
        )
        logger.error(
            "No se pudo entregar una invitación de equipo; revisar configuración de correo."
        )


@transaction.atomic
def create_invitation(*, tenant_id, actor, email, role, request=None):
    tenant, manager = lock_company(tenant_id, actor=actor)
    authorize_role(manager, role)
    email = email.strip().lower()
    if Membership.objects.filter(tenant=tenant, user__email=email, is_active=True).exists():
        raise ValidationError(
            {"email": "Ese usuario ya tiene una membresía activa en esta empresa."}
        )
    pending = TenantInvitation.objects.filter(tenant=tenant, email=email, status="pending").first()
    if pending:
        if pending.expires_at > timezone.now():
            raise ValidationError(
                {"email": "Ya existe una invitación pendiente. Podés reenviarla o revocarla."}
            )
        pending.status = "revoked"
        pending.save(update_fields=["status", "updated_at"])
    token = secrets.token_urlsafe(32)
    invitation = TenantInvitation.objects.create(
        tenant=tenant,
        email=email,
        role=role,
        token_digest=token_digest(token),
        invited_by=actor,
        expires_at=timezone.now() + timedelta(days=7),
    )
    record_audit_event(
        action=AuditEvent.Action.CREATE,
        entity_type="tenancy.invitation",
        entity_id=str(invitation.pk),
        tenant=tenant,
        actor=actor,
        request=request,
        metadata={"role": role},
    )
    transaction.on_commit(lambda: deliver_invitation(invitation.pk, token))
    return invitation


@transaction.atomic
def manage_invitation(*, tenant_id, actor, invitation_id, resend=False, request=None):
    tenant, manager = lock_company(tenant_id, actor=actor)
    invitation = (
        TenantInvitation.objects.select_for_update().filter(pk=invitation_id, tenant=tenant).first()
    )
    if invitation is None:
        raise NotFound("La invitación no está disponible.")
    authorize_role(manager, invitation.role)
    if invitation.status != "pending":
        raise ValidationError("Solo se pueden administrar invitaciones pendientes o vencidas.")
    if resend:
        token = secrets.token_urlsafe(32)
        invitation.token_digest = token_digest(token)
        invitation.expires_at = timezone.now() + timedelta(days=7)
        invitation.delivery_status = "pending"
        invitation.sent_at = None
        invitation.invited_by = actor
        transaction.on_commit(lambda: deliver_invitation(invitation.pk, token))
    else:
        invitation.status = "revoked"
    invitation.save()
    record_audit_event(
        action=AuditEvent.Action.UPDATE,
        entity_type="tenancy.invitation",
        entity_id=str(invitation.pk),
        tenant=tenant,
        actor=actor,
        request=request,
        metadata={"event": "resent" if resend else "revoked"},
    )
    return invitation


def valid_invitation(token, *, lock=False):
    digest = token_digest(token)
    queryset = TenantInvitation.objects.select_related("tenant")
    if lock:
        # Lock the tenant first, matching every other enterprise mutation.
        tenant_id = queryset.filter(token_digest=digest).values_list("tenant_id", flat=True).first()
        if tenant_id:
            Tenant.objects.select_for_update().filter(pk=tenant_id).first()
        queryset = queryset.select_for_update(of=("self",))
    invitation = queryset.filter(
        token_digest=digest, status="pending", tenant__is_active=True, expires_at__gt=timezone.now()
    ).first()
    if invitation is None:
        raise ValidationError({"token": INVALID_INVITATION})
    inviter = Membership.objects.filter(
        tenant=invitation.tenant,
        user_id=invitation.invited_by_id,
        user__is_active=True,
        is_active=True,
        role__in=MANAGERS,
    ).first()
    if inviter is None or (invitation.role in MANAGERS and inviter.role != "owner"):
        raise ValidationError({"token": INVALID_INVITATION})
    return invitation


@transaction.atomic
def accept_invitation(
    *,
    token,
    actor=None,
    first_name="",
    last_name="",
    password="",
    password_confirm="",
    request=None,
):
    invitation = valid_invitation(token)
    User = get_user_model()
    if actor and actor.is_authenticated:
        user = (
            User.objects.select_for_update(no_key=True)
            .filter(pk=actor.pk, is_active=True, email=invitation.email)
            .first()
        )
        if user is None:
            raise PermissionDenied("Iniciá sesión con la cuenta destinataria de la invitación.")
    else:
        if User.objects.filter(email=invitation.email).exists():
            raise ValidationError(
                {"email": "La cuenta ya existe. Iniciá sesión para aceptar la invitación."}
            )
        if not first_name.strip() or not password or password != password_confirm:
            raise ValidationError(
                {"password": "Completá tu nombre y dos contraseñas coincidentes."}
            )
        user = User(
            email=invitation.email, first_name=first_name.strip(), last_name=last_name.strip()
        )
        try:
            validate_password(password, user=user)
        except PasswordValidationError as exc:
            raise ValidationError({"password": exc.messages}) from exc
        user.set_password(password)
        try:
            with transaction.atomic():
                user.save()
        except IntegrityError as exc:
            raise ValidationError(
                {"email": "La cuenta ya existe. Iniciá sesión para aceptar."}
            ) from exc
    # Account first, tenant second: concurrent account deactivation cannot miss
    # a newly accepted membership or deadlock with team administration.
    invitation = valid_invitation(token, lock=True)
    member = (
        Membership.objects.select_for_update().filter(tenant=invitation.tenant, user=user).first()
    )
    if member and member.is_active:
        raise ValidationError("Ya tenés una membresía activa en esta empresa.")
    if member:
        member.role, member.is_active = invitation.role, True
        member.save(update_fields=["role", "is_active", "updated_at"])
    else:
        member = Membership.objects.create(
            tenant=invitation.tenant, user=user, role=invitation.role
        )
    invitation.status, invitation.accepted_by, invitation.accepted_at = (
        "accepted",
        user,
        timezone.now(),
    )
    invitation.save(update_fields=["status", "accepted_by", "accepted_at", "updated_at"])
    record_audit_event(
        action=AuditEvent.Action.UPDATE,
        entity_type="tenancy.invitation",
        entity_id=str(invitation.pk),
        tenant=invitation.tenant,
        actor=user,
        request=request,
        metadata={"event": "accepted", "role": member.role},
    )
    record_audit_event(
        action=AuditEvent.Action.CREATE,
        entity_type="tenancy.membership",
        entity_id=str(member.pk),
        tenant=invitation.tenant,
        actor=user,
        request=request,
        metadata={"source": "invitation", "role": member.role},
    )
    return user, member
