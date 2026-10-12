import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from tenancy.models import Tenant


class AuditEvent(models.Model):
    """
    Evento de auditoría de la plataforma.

    Los eventos se diseñan como registros de solo anexado:
    se pueden crear y consultar, pero no modificar ni eliminar
    mediante las operaciones normales de instancia del modelo.
    """

    class Action(models.TextChoices):
        CREATE = "create", "Creación"
        UPDATE = "update", "Modificación"
        DEACTIVATE = "deactivate", "Desactivación"
        DELETE = "delete", "Eliminación"
        LOGIN = "login", "Inicio de sesión"
        LOGOUT = "logout", "Cierre de sesión"
        PERMISSION_DENIED = "permission_denied", "Acceso denegado"
        EXPORT = "export", "Exportación"
        ISSUE = "issue", "Emisión"
        PAYMENT = "payment", "Pago"
        SYSTEM = "system", "Sistema"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        null=True,
        blank=True,
    )

    action = models.CharField(
        max_length=30,
        choices=Action.choices,
    )

    entity_type = models.CharField(
        max_length=100,
    )

    entity_id = models.CharField(
        max_length=100,
        blank=True,
    )

    changes = models.JSONField(
        default=dict,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    request_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
    )

    user_agent = models.CharField(
        max_length=512,
        blank=True,
    )

    occurred_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        verbose_name = "evento de auditoría"
        verbose_name_plural = "eventos de auditoría"
        ordering = ["-occurred_at"]

        indexes = [
            models.Index(
                fields=["tenant", "occurred_at"],
                name="audit_tenant_time_idx",
            ),
            models.Index(
                fields=[
                    "tenant",
                    "entity_type",
                    "entity_id",
                ],
                name="audit_tenant_entity_idx",
            ),
            models.Index(
                fields=["actor", "occurred_at"],
                name="audit_actor_time_idx",
            ),
            models.Index(
                fields=["action", "occurred_at"],
                name="audit_action_time_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Los eventos de auditoría no se pueden modificar.")

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los eventos de auditoría no se pueden eliminar desde la aplicación.")

    def __str__(self):
        return f"{self.action} - {self.entity_type} - {self.occurred_at}"
