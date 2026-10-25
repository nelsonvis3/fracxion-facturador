from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied, ValidationError


class TenantQuerySetMixin:
    """
    Limita las consultas y escrituras a la empresa autorizada.

    Requiere que la vista utilice TenantAccessPermission
    y que sus modelos tengan una relación llamada 'tenant'.

    Las vistas que utilicen este mixin deben definir un queryset.
    """

    tenant_field = "tenant"

    def get_authorized_tenant(self):
        """
        Obtiene el tenant validado por TenantAccessPermission.
        Deniega el acceso si el contexto no es válido.
        """
        request = self.request

        user = getattr(request, "user", None)
        tenant = getattr(request, "tenant", None)
        membership = getattr(request, "membership", None)

        if user is None or not user.is_authenticated or tenant is None or membership is None:
            raise PermissionDenied("No existe un contexto de empresa autorizado.")

        if (
            membership.user_id != user.pk
            or membership.tenant_id != tenant.pk
            or not membership.is_active
            or not tenant.is_active
        ):
            raise PermissionDenied("La membresía o la empresa no están activas.")

        return tenant

    def get_queryset(self):
        """
        Devuelve exclusivamente objetos de la empresa autorizada.
        """
        # drf-spectacular utiliza vistas simuladas para generar
        # documentación. Nunca exponemos datos en ese contexto.
        if getattr(self, "swagger_fake_view", False):
            return super().get_queryset().none()

        queryset = super().get_queryset()
        tenant = self.get_authorized_tenant()

        try:
            queryset.model._meta.get_field(self.tenant_field)
        except Exception as exc:
            raise ImproperlyConfigured(
                f"El modelo de {self.__class__.__name__} debe tener "
                f"un campo llamado '{self.tenant_field}'."
            ) from exc

        queryset = queryset.filter(**{self.tenant_field: tenant})
        if getattr(self, "_lock_for_update", False):
            queryset = queryset.select_for_update(of=("self",))
        return queryset

    def perform_create(self, serializer):
        """
        Asigna la empresa desde el contexto autorizado del servidor.
        No confía en el tenant enviado por el cliente.
        """
        tenant = self.get_authorized_tenant()

        serializer.save(**{self.tenant_field: tenant})

    def perform_update(self, serializer):
        """
        Conserva la empresa autorizada durante las modificaciones.
        """
        tenant = self.get_authorized_tenant()

        serializer.save(**{self.tenant_field: tenant})


class TenantMutationMixin(TenantQuerySetMixin):
    """Operaciones de escritura con locks y conflictos de unicidad legibles."""

    def _handle_integrity_error(self, exc):
        constraint = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", "")
        messages = {
            "uniq_cust_doc_tenant": {
                "document_number": "Ya existe un cliente con ese documento en esta empresa."
            },
            "uniq_product_sku_tenant": {"sku": "Este SKU ya está registrado en la empresa."},
        }
        if constraint in messages:
            raise ValidationError(messages[constraint]) from exc
        raise exc

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                from .services import lock_company

                lock_company(self.get_authorized_tenant().pk, actor=request.user)
                return super().create(request, *args, **kwargs)
        except IntegrityError as exc:
            self._handle_integrity_error(exc)

    def update(self, request, *args, **kwargs):
        # Leer y validar después de obtener el lock evita sobrescribir un PATCH concurrente.
        try:
            with transaction.atomic():
                from .services import lock_company

                lock_company(self.get_authorized_tenant().pk, actor=request.user)
                self._lock_for_update = True
                return super().update(request, *args, **kwargs)
        except IntegrityError as exc:
            self._handle_integrity_error(exc)
        finally:
            self._lock_for_update = False
