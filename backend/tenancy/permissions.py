from django.core.exceptions import ValidationError
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Membership


class TenantAccessPermission(BasePermission):
    """
    Verifica que el usuario tenga una membresía activa
    en la empresa solicitada y que su rol permita la operación.

    La URL debe contener el parámetro tenant_id.
    """

    message = "No tenés permisos para acceder a esta empresa."

    READ_ROLES = frozenset(Membership.Role.values)

    # Por defecto, solamente los roles administrativos pueden escribir.
    DEFAULT_WRITE_ROLES = frozenset(
        {
            Membership.Role.OWNER,
            Membership.Role.ADMIN,
        }
    )

    # Las eliminaciones requieren un rol administrativo.
    DELETE_ROLES = frozenset(
        {
            Membership.Role.OWNER,
            Membership.Role.ADMIN,
        }
    )

    def has_permission(self, request, view):
        # 1. Exigir un usuario autenticado.
        if not request.user or not request.user.is_authenticated:
            return False
        if not getattr(request.user, "is_active", False):
            return False

        # 2. Obtener la empresa exclusivamente de la ruta.
        tenant_url_kwarg = getattr(
            view,
            "tenant_url_kwarg",
            "tenant_id",
        )
        tenant_id = view.kwargs.get(tenant_url_kwarg)

        if not tenant_id:
            return False

        # 3. Buscar una membresía activa de ese usuario.
        # También comprobamos que la empresa esté activa.
        try:
            membership = (
                Membership.objects.select_related("tenant")
                .filter(
                    tenant_id=tenant_id,
                    tenant__is_active=True,
                    user=request.user,
                    is_active=True,
                )
                .first()
            )
        except (ValidationError, ValueError, TypeError):
            return False

        if membership is None:
            return False

        # 4. Guardar el contexto validado para la vista.
        request.tenant = membership.tenant
        request.membership = membership

        # 5. Determinar qué roles puede utilizar esta operación.
        action = getattr(view, "action", None)

        # Las vistas pueden definir excepciones explícitas por acción.
        role_policy = getattr(
            view,
            "tenant_roles_by_action",
            {},
        )

        policy_key = action or request.method.lower()
        required_roles = role_policy.get(policy_key)

        # 6. Aplicar la política predeterminada si no hay excepción.
        if required_roles is None:
            if request.method in SAFE_METHODS:
                required_roles = self.READ_ROLES

            elif request.method == "DELETE" or action == "destroy":
                required_roles = self.DELETE_ROLES

            else:
                required_roles = self.DEFAULT_WRITE_ROLES

        # 7. Denegar por defecto si el rol no está autorizado.
        return membership.role in required_roles
