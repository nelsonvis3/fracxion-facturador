from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db.models import F
from django.utils import timezone
from rest_framework import serializers

from tenancy.models import BusinessSettings


def business_today(tenant_id):
    zone = (
        BusinessSettings.objects.filter(tenant_id=tenant_id)
        .values_list("timezone", flat=True)
        .first()
        or "America/Argentina/Cordoba"
    )
    return timezone.localdate(timezone=ZoneInfo(zone))


def receivable_status(invoice, balance, today=None):
    if invoice.status != "issued":
        return "draft"
    if balance <= 0:
        return "paid"
    if invoice.due_date is None:
        return "unscheduled"
    today = today or business_today(invoice.tenant_id)
    return (
        "overdue"
        if invoice.due_date < today
        else "due_today"
        if invoice.due_date == today
        else "upcoming"
    )


class ReceivableFilters(serializers.Serializer):
    receivable = serializers.ChoiceField(
        choices=["overdue", "due_today", "upcoming", "unscheduled", "paid", "unpaid"],
        required=False,
    )
    due_from = serializers.DateField(required=False)
    due_to = serializers.DateField(required=False)
    due_window = serializers.IntegerField(required=False, min_value=1, max_value=365, default=7)
    customer = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if attrs.get("due_from") and attrs.get("due_to") and attrs["due_from"] > attrs["due_to"]:
            raise serializers.ValidationError("El rango de vencimiento no es válido.")
        return attrs


def filter_receivables(queryset, params, today):
    serializer = ReceivableFilters(data=params)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    for field, lookup in [
        ("due_from", "due_date__gte"),
        ("due_to", "due_date__lte"),
        ("customer", "customer_id"),
    ]:
        if field in values:
            queryset = queryset.filter(**{lookup: values[field]})
    state = values.get("receivable")
    if state:
        queryset = queryset.filter(status="issued")
        if state == "paid":
            return queryset.filter(total__lte=F("paid_amount"))
        queryset = queryset.filter(total__gt=F("paid_amount"))
        if state == "overdue":
            queryset = queryset.filter(due_date__lt=today)
        elif state == "due_today":
            queryset = queryset.filter(due_date=today)
        elif state == "upcoming":
            queryset = queryset.filter(
                due_date__gt=today, due_date__lte=today + timedelta(days=values["due_window"])
            )
        elif state == "unscheduled":
            queryset = queryset.filter(due_date__isnull=True)
    return queryset
