"""Durable PostgreSQL jobs. Only explicitly registered, bounded operations run."""

import json
import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from analytics.services import invoices_with_balances, reporting_context
from auditlog.models import AuditEvent
from auditlog.services import record_audit_event
from reports.services import ReportFilters, ReportTooLarge, dataset, render_report
from tenancy.models import BusinessSettings, Membership
from tenancy.services import lock_company

from .models import AutomationRule, Job, JobAttempt, Notification

ANALYSTS = {"owner", "admin", "accountant"}
MAX_ATTEMPTS = 3
LEASE = timedelta(minutes=10)


def normalized_report(tenant, params):
    serializer = ReportFilters(data=params)
    serializer.is_valid(raise_exception=True)
    values, _, _ = reporting_context(tenant, params)
    return json.loads(json.dumps(values | serializer.validated_data, cls=DjangoJSONEncoder))


@transaction.atomic
def request_report(*, tenant_id, actor, params, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor, roles=ANALYSTS)
    if (
        Job.objects.filter(
            tenant=tenant, requested_by=actor, status__in=["pending", "running"]
        ).count()
        >= 5
    ):
        raise ValidationError("Ya tenés cinco informes pendientes. Esperá a que terminen.")
    payload = normalized_report(tenant, params)
    job = Job.objects.create(
        tenant=tenant,
        requested_by=actor,
        kind="report",
        dedupe_key=f"manual:{uuid.uuid4()}",
        payload=payload,
        available_at=timezone.now(),
    )
    record_audit_event(
        tenant=tenant,
        actor=actor,
        request=request,
        action=AuditEvent.Action.CREATE,
        entity_type="automation.job",
        entity_id=job.pk,
        metadata={"kind": "report", "filters": payload},
    )
    return job


def next_occurrence(rule, zone, after):
    local = after.astimezone(zone)
    day = local.date()
    if rule.frequency == "weekly":
        day += timedelta(days=(7 - day.weekday()) % 7)
    elif rule.frequency == "monthly":
        day = day.replace(day=1)
    candidate = datetime.combine(day, time(rule.hour), tzinfo=zone)
    if candidate <= after:
        if rule.frequency == "daily":
            day += timedelta(days=1)
        elif rule.frequency == "weekly":
            day += timedelta(days=7)
        else:
            day = day.replace(year=day.year + (day.month == 12), month=day.month % 12 + 1, day=1)
        candidate = datetime.combine(day, time(rule.hour), tzinfo=zone)
    return candidate


@transaction.atomic
def save_rule(*, tenant_id, actor, data, rule_id=None, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor)
    if rule_id:
        rule = AutomationRule.objects.select_for_update().filter(tenant=tenant, pk=rule_id).first()
        if rule is None:
            raise NotFound()
    else:
        if AutomationRule.objects.filter(tenant=tenant).count() >= 20:
            raise ValidationError("La empresa admite hasta veinte automatizaciones.")
        rule = AutomationRule(tenant=tenant, owner=actor)
    for key in ["name", "kind", "frequency", "hour", "enabled"]:
        if key in data:
            setattr(rule, key, data[key])
    if rule.kind == "report":
        # Schedules use the last fully closed business period, never fixed demo dates.
        options = data.get("options", rule.options)
        allowed = {
            key: value
            for key, value in options.items()
            if key in {"kind", "file_format", "currency"}
        }
        checked = ReportFilters(data=allowed)
        checked.is_valid(raise_exception=True)
        rule.options = checked.validated_data
    else:
        rule.options = {}
    # Saving transfers responsibility to the current authorized manager.
    rule.owner = actor
    preferences = BusinessSettings.objects.filter(tenant=tenant).first() or BusinessSettings(
        tenant=tenant
    )
    rule.next_run_at = next_occurrence(rule, ZoneInfo(preferences.timezone), timezone.now())
    rule.save()
    record_audit_event(
        tenant=tenant,
        actor=actor,
        request=request,
        action=AuditEvent.Action.UPDATE if rule_id else AuditEvent.Action.CREATE,
        entity_type="automation.rule",
        entity_id=rule.pk,
        metadata={"kind": rule.kind, "enabled": rule.enabled, "frequency": rule.frequency},
    )
    return rule


def schedule_due(*, now=None, limit=100):
    from tenancy.models import Tenant

    now = now or timezone.now()
    candidates = list(
        AutomationRule.objects.filter(enabled=True, next_run_at__lte=now)
        .order_by("next_run_at")
        .values_list("pk", "tenant_id")[:limit]
    )
    count = 0
    for rule_id, tenant_id in candidates:
        with transaction.atomic():
            # Lock tenant before rule, matching settings and team operations.
            tenant = (
                Tenant.objects.select_for_update(skip_locked=True)
                .filter(pk=tenant_id, is_active=True)
                .first()
            )
            if tenant is None:
                continue
            rule = (
                AutomationRule.objects.select_for_update(skip_locked=True)
                .filter(pk=rule_id, enabled=True, next_run_at__lte=now)
                .first()
            )
            if rule is None:
                continue
            preferences = BusinessSettings.objects.filter(
                tenant=tenant
            ).first() or BusinessSettings(tenant=tenant)
            zone = ZoneInfo(preferences.timezone)
            # After downtime, generate one catch-up for the most recent complete period.
            # Missed intervals are explicitly coalesced, never silently replayed in bulk.
            day = now.astimezone(zone).date()
            payload = {}
            if rule.kind == "report":
                end = (day.replace(day=1) if rule.frequency == "monthly" else day) - timedelta(
                    days=1
                )
                start = (
                    end
                    if rule.frequency == "daily"
                    else day - timedelta(days=7)
                    if rule.frequency == "weekly"
                    else end.replace(day=1)
                )
                payload = normalized_report(
                    tenant, rule.options | {"date_from": str(start), "date_to": str(end)}
                )
            Job.objects.get_or_create(
                tenant=tenant,
                dedupe_key=f"rule:{rule.pk}:{rule.next_run_at.isoformat()}",
                defaults={
                    "requested_by_id": rule.owner_id,
                    "rule": rule,
                    "kind": rule.kind,
                    "payload": payload,
                    "available_at": now,
                },
            )
            rule.last_run_at = now
            rule.next_run_at = next_occurrence(rule, zone, now)
            rule.save(update_fields=["last_run_at", "next_run_at", "updated_at"])
            count += 1
    return count


@transaction.atomic
def claim_job(*, now=None, job_id=None):
    now = now or timezone.now()
    eligible = Q(status="pending", available_at__lte=now) | Q(status="running", lease_until__lt=now)
    query = Job.objects.select_for_update(skip_locked=True).filter(eligible)
    if job_id:
        query = query.filter(pk=job_id)
    job = query.order_by("available_at", "pk").first()
    if job is None:
        return None
    if job.status == "running":
        JobAttempt.objects.filter(job=job, lease_id=job.lease_id, outcome="running").update(
            outcome="lease_expired", finished_at=now
        )
    if job.attempts >= MAX_ATTEMPTS:
        job.status = "failed"
        job.error_code = "worker_timeout"
        job.finished_at = now
        job.lease_id = None
        job.lease_until = None
        job.save()
        return None
    job.attempts += 1
    job.status = "running"
    job.started_at = now
    job.lease_id = uuid.uuid4()
    job.lease_until = now + LEASE
    job.save()
    JobAttempt.objects.create(job=job, number=job.attempts, lease_id=job.lease_id, started_at=now)
    return job


def notify(*, tenant, recipient, key, title, message, invoice=None, job=None):
    return Notification.objects.get_or_create(
        tenant=tenant,
        recipient=recipient,
        dedupe_key=key,
        defaults={"title": title, "message": message, "invoice": invoice, "job": job},
    )[0]


def authorized_job(job):
    return Membership.objects.filter(
        tenant_id=job.tenant_id,
        tenant__is_active=True,
        user_id=job.requested_by_id,
        user__is_active=True,
        is_active=True,
        role__in=ANALYSTS if job.kind == "report" else {"owner", "admin"},
    ).exists() and (
        not job.rule_id
        or AutomationRule.objects.filter(
            pk=job.rule_id, tenant_id=job.tenant_id, enabled=True, kind=job.kind
        ).exists()
    )


def execute_job(job):
    """A lease fences stale workers; financial models are never modified here."""
    content = None
    data = None
    try:
        if not authorized_job(job):
            raise PermissionDenied()
        if job.kind == "report":
            data = dataset(job.tenant, job.payload, max_rows=10000)
            content = render_report(data, job.payload.get("file_format", "csv"))
            if len(content) > 20 * 1024 * 1024:
                raise ReportTooLarge()
        elif job.kind != "reminders":
            raise ValidationError("unsupported_job")
        with transaction.atomic():
            # Same lock order as company operations; never hold a job while waiting on a tenant.
            tenant, _ = lock_company(job.tenant_id, actor=job.requested_by, roles=ANALYSTS)
            current = Job.objects.select_for_update().get(pk=job.pk)
            if (
                current.lease_id != job.lease_id
                or current.status != "running"
                or current.lease_until <= timezone.now()
            ):
                return False
            if not authorized_job(current):
                raise PermissionDenied()
            if job.kind == "report":
                current.result = content
                current.result_format = job.payload.get("file_format", "csv")
                current.result_filename = f"fracxion-{data['kind']}-{data['date_from']}-{data['date_to']}.{current.result_format}"
                current.result_expires_at = timezone.now() + timedelta(days=7)
                notify(
                    tenant=tenant,
                    recipient=job.requested_by,
                    key=f"report:{job.pk}",
                    title="Informe disponible",
                    message="Tu informe está listo para descargar durante siete días.",
                    job=current,
                )
            else:
                preferences = BusinessSettings.objects.filter(
                    tenant=tenant
                ).first() or BusinessSettings(tenant=tenant)
                if preferences.payment_reminders_enabled:
                    today = timezone.localdate(timezone=ZoneInfo(preferences.timezone))
                    invoices = list(
                        invoices_with_balances(tenant, None)
                        .filter(current_balance__gt=0, due_date__lte=today + timedelta(days=3))
                        .order_by("due_date", "pk")[:1001]
                    )
                    if len(invoices) > 1000:
                        raise ReportTooLarge()
                    recipients = Membership.objects.filter(
                        tenant=tenant, is_active=True, user__is_active=True, role__in=ANALYSTS
                    ).select_related("user")
                    for member in recipients:
                        for invoice in invoices:
                            notify(
                                tenant=tenant,
                                recipient=member.user,
                                key=f"due:{invoice.pk}:{today}",
                                title="Factura interna vencida"
                                if invoice.due_date < today
                                else "Vencimiento próximo",
                                message=f"Documento #{invoice.internal_number} · saldo {invoice.current_balance:.2f} {invoice.currency} · vence {invoice.due_date.isoformat()}",
                                invoice=invoice,
                            )
            current.status = "succeeded"
            current.error_code = ""
            current.finished_at = timezone.now()
            current.lease_until = None
            current.save()
            JobAttempt.objects.filter(job=current, lease_id=job.lease_id).update(
                outcome="succeeded", finished_at=current.finished_at
            )
            record_audit_event(
                tenant=tenant,
                actor=job.requested_by,
                action=AuditEvent.Action.SYSTEM,
                entity_type="automation.job",
                entity_id=current.pk,
                metadata={
                    "kind": current.kind,
                    "outcome": "succeeded",
                    "attempt": current.attempts,
                },
            )
        return True
    except Exception as exc:
        code = (
            "permission_revoked"
            if isinstance(exc, PermissionDenied)
            else "report_limit"
            if isinstance(exc, ReportTooLarge)
            else "invalid_job"
            if isinstance(exc, ValidationError)
            else "execution_failed"
        )
        with transaction.atomic():
            current = Job.objects.select_for_update().get(pk=job.pk)
            if current.lease_id != job.lease_id or current.status != "running":
                return False
            terminal = code != "execution_failed" or current.attempts >= MAX_ATTEMPTS
            current.status = (
                "cancelled" if code == "permission_revoked" else "failed" if terminal else "pending"
            )
            current.error_code = code
            current.available_at = timezone.now() + timedelta(
                seconds=30 * 2 ** (current.attempts - 1)
            )
            current.lease_until = None
            current.finished_at = timezone.now() if terminal else None
            current.save()
            JobAttempt.objects.filter(job=current, lease_id=job.lease_id).update(
                outcome=code, finished_at=timezone.now()
            )
        return False


@transaction.atomic
def retry_job(*, tenant_id, actor, job_id, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor, roles=ANALYSTS)
    job = (
        Job.objects.select_for_update()
        .filter(tenant=tenant, requested_by=actor, pk=job_id, status__in=["failed", "cancelled"])
        .first()
    )
    if job is None:
        raise NotFound()
    # Preserve all previous attempts; the retry is a new, separately audited request.
    if job.kind != "report":
        raise ValidationError("Reactivá la regla para futuras ejecuciones.")
    return request_report(tenant_id=tenant_id, actor=actor, params=job.payload, request=request)
