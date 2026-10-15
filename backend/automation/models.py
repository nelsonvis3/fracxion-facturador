import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class AutomationRule(models.Model):
    class Kind(models.TextChoices):
        REMINDERS = "reminders", "Alertas internas de vencimiento"
        REPORT = "report", "Informe programado"

    class Frequency(models.TextChoices):
        DAILY = "daily", "Diaria"
        WEEKLY = "weekly", "Semanal"
        MONTHLY = "monthly", "Mensual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    frequency = models.CharField(max_length=16, choices=Frequency.choices)
    hour = models.PositiveSmallIntegerField(default=9)
    enabled = models.BooleanField(default=False)
    options = models.JSONField(default=dict)
    next_run_at = models.DateTimeField()
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(hour__lte=23), name="automation_hour_valid")
        ]
        indexes = [models.Index(fields=["enabled", "next_run_at"], name="automation_due_idx")]


class Job(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        RUNNING = "running", "En ejecución"
        SUCCEEDED = "succeeded", "Completado"
        FAILED = "failed", "Fallido"
        CANCELLED = "cancelled", "Cancelado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    rule = models.ForeignKey(AutomationRule, on_delete=models.PROTECT, null=True, blank=True)
    kind = models.CharField(max_length=16, choices=AutomationRule.Kind.choices)
    dedupe_key = models.CharField(max_length=160)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField()
    lease_until = models.DateTimeField(null=True, blank=True)
    lease_id = models.UUIDField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    result = models.BinaryField(null=True, blank=True)
    result_format = models.CharField(max_length=8, blank=True)
    result_filename = models.CharField(max_length=160, blank=True)
    result_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "dedupe_key"], name="unique_tenant_job_key")
        ]
        indexes = [
            models.Index(fields=["status", "available_at"], name="job_available_idx"),
            models.Index(fields=["tenant", "-created_at"], name="job_tenant_created_idx"),
        ]


class JobAttempt(models.Model):
    job = models.ForeignKey(Job, on_delete=models.PROTECT, related_name="executions")
    number = models.PositiveSmallIntegerField()
    lease_id = models.UUIDField(unique=True)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=32, default="running")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["job", "number"], name="unique_job_attempt")]
        ordering = ["-number"]


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    dedupe_key = models.CharField(max_length=180)
    title = models.CharField(max_length=160)
    message = models.CharField(max_length=1000)
    invoice = models.ForeignKey("billing.Invoice", on_delete=models.PROTECT, null=True, blank=True)
    job = models.ForeignKey(Job, on_delete=models.PROTECT, null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "recipient", "dedupe_key"], name="unique_notification_effect"
            )
        ]
        indexes = [
            models.Index(
                fields=["tenant", "recipient", "read_at", "-created_at"],
                name="notification_inbox_idx",
            )
        ]


class WorkerHeartbeat(models.Model):
    name = models.CharField(max_length=255, primary_key=True)
    seen_at = models.DateTimeField()
