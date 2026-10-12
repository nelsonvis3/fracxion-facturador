import uuid

from django.conf import settings
from django.db import models


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
