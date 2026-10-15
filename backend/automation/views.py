from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, Throttled, ValidationError
from rest_framework.response import Response

from accounts.rate_limits import is_rate_limited
from auditlog.models import AuditEvent
from auditlog.services import record_audit_event
from reports.services import MIME_TYPES, ReportFilters
from tenancy.permissions import TenantAccessPermission
from tenancy.services import lock_company

from .models import AutomationRule, Job, Notification
from .serializers import JobSerializer, NotificationSerializer, RuleSerializer
from .services import ANALYSTS, request_report, retry_job, save_rule


class RuleViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    permission_classes = [TenantAccessPermission]
    tenant_roles_by_action = {
        "list": {"owner", "admin"},
        "create": {"owner", "admin"},
        "partial_update": {"owner", "admin"},
        "update": {"owner", "admin"},
    }
    serializer_class = RuleSerializer
    queryset = AutomationRule.objects.none()
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return AutomationRule.objects.filter(tenant=self.request.tenant).order_by("name", "pk")

    def perform_create(self, serializer):
        serializer.instance = save_rule(
            tenant_id=self.request.tenant.pk,
            actor=self.request.user,
            data=serializer.validated_data,
            request=self.request,
        )

    def perform_update(self, serializer):
        serializer.instance = save_rule(
            tenant_id=self.request.tenant.pk,
            actor=self.request.user,
            rule_id=serializer.instance.pk,
            data=serializer.validated_data,
            request=self.request,
        )


class JobViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [TenantAccessPermission]
    tenant_roles_by_action = {
        name: ANALYSTS for name in ["list", "retrieve", "create", "download", "retry"]
    }
    serializer_class = JobSerializer
    queryset = Job.objects.none()
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return (
            Job.objects.filter(tenant=self.request.tenant, requested_by=self.request.user)
            .defer("result")
            .prefetch_related("executions")
        )

    @extend_schema(request=ReportFilters, responses={202: JobSerializer})
    def create(self, request, tenant_id):
        if is_rate_limited(
            request, action="export_jobs", limit=10, identity=f"{tenant_id}:{request.user.pk}"
        ):
            raise Throttled(wait=900)
        job = request_report(
            tenant_id=tenant_id, actor=request.user, params=request.data, request=request
        )
        return Response(JobSerializer(job).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    @action(detail=True, methods=["get"])
    @transaction.atomic
    def download(self, request, tenant_id, pk=None):
        lock_company(tenant_id, actor=request.user, roles=ANALYSTS)
        if is_rate_limited(
            request, action="private_downloads", limit=60, identity=f"{tenant_id}:{request.user.pk}"
        ):
            raise Throttled(wait=900)
        job = self.get_object()
        if (
            job.status != "succeeded"
            or not job.result_expires_at
            or job.result_expires_at <= timezone.now()
        ):
            raise NotFound("El archivo no está disponible o venció. Generá un informe nuevo.")
        if job.result is None:
            raise NotFound()
        record_audit_event(
            tenant=request.tenant,
            actor=request.user,
            request=request,
            action=AuditEvent.Action.EXPORT,
            entity_type="reports.download",
            entity_id=job.pk,
            metadata={"format": job.result_format},
        )
        response = HttpResponse(bytes(job.result), content_type=MIME_TYPES[job.result_format])
        response["Content-Disposition"] = f'attachment; filename="{job.result_filename}"'
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @extend_schema(request=None, responses={202: JobSerializer})
    @action(detail=True, methods=["post"])
    def retry(self, request, tenant_id, pk=None):
        job = retry_job(tenant_id=tenant_id, actor=request.user, job_id=pk, request=request)
        return Response(JobSerializer(job).data, status=202)


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [TenantAccessPermission]
    serializer_class = NotificationSerializer
    queryset = Notification.objects.none()
    http_method_names = ["get", "post", "head", "options"]
    tenant_roles_by_action = {"mark_read": set(["owner", "admin", "accountant", "sales", "viewer"])}

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        query = Notification.objects.filter(tenant=self.request.tenant, recipient=self.request.user)
        unread = self.request.query_params.get("unread")
        if unread not in {None, "true", "false"}:
            raise ValidationError({"unread": "Usá true o false."})
        if unread == "true":
            query = query.filter(read_at__isnull=True)
        return query

    @extend_schema(request=None, responses={200: NotificationSerializer})
    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, tenant_id, pk=None):
        item = self.get_object()
        Notification.objects.filter(pk=item.pk, read_at__isnull=True).update(read_at=timezone.now())
        item.refresh_from_db()
        return Response(self.get_serializer(item).data)
