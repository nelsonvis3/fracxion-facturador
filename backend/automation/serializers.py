from rest_framework import serializers

from tenancy.serializers import StrictInputMixin

from .models import AutomationRule, Job, JobAttempt, Notification


class RuleSerializer(StrictInputMixin, serializers.ModelSerializer):
    options = serializers.DictField(required=False)

    class Meta:
        model = AutomationRule
        fields = [
            "id",
            "name",
            "kind",
            "frequency",
            "hour",
            "enabled",
            "options",
            "next_run_at",
            "last_run_at",
            "created_at",
        ]
        read_only_fields = ["id", "next_run_at", "last_run_at", "created_at"]
        extra_kwargs = {
            "hour": {"min_value": 0, "max_value": 23},
            "enabled": {"default": False},
            "frequency": {"required": True},
            "kind": {"required": True},
        }


class JobAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobAttempt
        fields = ["number", "started_at", "finished_at", "outcome"]


class JobSerializer(serializers.ModelSerializer):
    executions = JobAttemptSerializer(many=True, read_only=True)

    class Meta:
        model = Job
        fields = [
            "id",
            "kind",
            "payload",
            "status",
            "attempts",
            "available_at",
            "started_at",
            "finished_at",
            "error_code",
            "result_format",
            "result_filename",
            "result_expires_at",
            "created_at",
            "rule",
            "executions",
        ]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "message", "invoice", "job", "read_at", "created_at"]
