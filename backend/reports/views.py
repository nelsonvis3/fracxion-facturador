from django.db import transaction
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from accounts.rate_limits import is_rate_limited
from analytics.views import ANALYST_ROLES
from auditlog.models import AuditEvent
from auditlog.services import record_audit_event
from tenancy.permissions import TenantAccessPermission
from tenancy.services import lock_company

from .services import MIME_TYPES, ReportFilters, ReportTooLarge, dataset, render_report


class ExportView(APIView):
    permission_classes = [TenantAccessPermission]
    tenant_roles_by_action = {"get": ANALYST_ROLES}

    @extend_schema(parameters=[ReportFilters], responses={(200, "application/octet-stream"): bytes})
    def get(self, request, tenant_id):
        from rest_framework.exceptions import Throttled

        if is_rate_limited(
            request, action="exports", limit=10, identity=f"{tenant_id}:{request.user.pk}"
        ):
            raise Throttled(
                wait=900,
                detail="Alcanzaste el límite temporal de exportaciones. Reintentá más tarde.",
            )
        filters = ReportFilters(data=request.query_params)
        filters.is_valid(raise_exception=True)
        file_format = filters.validated_data["file_format"]
        try:
            data = dataset(request.tenant, request.query_params)
        except ReportTooLarge as exc:
            raise ValidationError(
                "Este informe supera el límite de descarga inmediata. Usá Generar informe para procesarlo en segundo plano."
            ) from exc
        content = render_report(data, file_format)
        with transaction.atomic():
            tenant, _ = lock_company(tenant_id, actor=request.user, roles=ANALYST_ROLES)
            record_audit_event(
                action=AuditEvent.Action.EXPORT,
                entity_type="reports.export",
                tenant=tenant,
                actor=request.user,
                request=request,
                metadata={
                    "kind": data["kind"],
                    "format": file_format,
                    "currency": data["currency"],
                    "date_from": data["date_from"],
                    "date_to": data["date_to"],
                    "rows": len(data["rows"]),
                },
            )
        response = HttpResponse(content, content_type=MIME_TYPES[file_format])
        response["Content-Disposition"] = (
            f'attachment; filename="fracxion-{data["kind"]}-{data["date_from"]}-{data["date_to"]}.{file_format}"'
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response
