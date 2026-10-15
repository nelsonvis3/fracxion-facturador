import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Tenant(models.Model):
    """Empresa que utiliza la plataforma SaaS."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        max_length=150,
    )

    slug = models.SlugField(
        max_length=100,
        unique=True,
    )

    legal_name = models.CharField(
        max_length=200,
        blank=True,
    )

    tax_id = models.CharField(
        max_length=20,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "empresa"
        verbose_name_plural = "empresas"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Membership(models.Model):
    """Relación entre un usuario y una empresa."""

    class Role(models.TextChoices):
        OWNER = "owner", "Propietario"
        ADMIN = "admin", "Administrador"
        ACCOUNTANT = "accountant", "Contador"
        SALES = "sales", "Ventas"
        VIEWER = "viewer", "Solo lectura"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "membresía"
        verbose_name_plural = "membresías"
        ordering = ["tenant__name", "user__email"]

        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user"],
                name="uniq_membership_tenant_user",
            ),
        ]

        indexes = [
            models.Index(
                fields=["tenant", "is_active"],
                name="membership_tenant_active_idx",
            ),
            models.Index(
                fields=["user", "is_active"],
                name="membership_user_active_idx",
            ),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.tenant.name} ({self.get_role_display()})"


class BusinessSettings(models.Model):
    tenant = models.OneToOneField(
        Tenant, primary_key=True, on_delete=models.PROTECT, related_name="business_settings"
    )
    country_code = models.CharField(max_length=2, default="AR")
    timezone = models.CharField(max_length=64, default="America/Argentina/Cordoba")
    default_currency = models.CharField(max_length=3, default="ARS")
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    website = models.URLField(blank=True)
    payment_terms_days = models.PositiveSmallIntegerField(null=True, blank=True)
    invoice_footer = models.CharField(max_length=1000, blank=True)
    payment_reminders_enabled = models.BooleanField(default=False)
    logo = models.BinaryField(null=True, editable=False)
    logo_updated_at = models.DateTimeField(null=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(payment_terms_days__isnull=True) | Q(payment_terms_days__lte=3650),
                name="settings_payment_terms_limit",
            )
        ]


class TenantInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        ACCEPTED = "accepted", "Aceptada"
        REVOKED = "revoked", "Revocada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Membership.Role.choices)
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="invitations_sent",
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations_accepted",
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    delivery_status = models.CharField(
        max_length=10,
        default="pending",
        choices=[("pending", "Pendiente"), ("sent", "Enviada"), ("failed", "Falló el envío")],
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "email"],
                condition=Q(status="pending"),
                name="uniq_pending_tenant_invitation",
            )
        ]
        indexes = [
            models.Index(
                fields=["tenant", "status", "expires_at"], name="tenant_invitation_state_idx"
            )
        ]
