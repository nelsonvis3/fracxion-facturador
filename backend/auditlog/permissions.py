from rest_framework.permissions import BasePermission

from tenancy.models import Membership
from tenancy.permissions import TenantAccessPermission


class AuditReadPermission(BasePermission):
    """
    Permite consultar auditorías únicamente a propietarios
    y administradores de la empresa autorizada.
    """

    message = "No tenés permisos para consultar la auditoría de esta empresa."

    ALLOWED_ROLES = frozenset(
        {
            Membership.Role.OWNER,
            Membership.Role.ADMIN,
        }
    )

    def has_permission(self, request, view):
        # Reutiliza la validación central de autenticación,
        # empresa activa y membresía activa.
        tenant_permission = TenantAccessPermission()

        if not tenant_permission.has_permission(request, view):
            return False

        membership = getattr(request, "membership", None)

        if membership is None:
            return False

        return membership.role in self.ALLOWED_ROLES
