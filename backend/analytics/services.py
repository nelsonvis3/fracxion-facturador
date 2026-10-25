"""Financial reporting reads business data, never writes financial state."""

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pycountry
from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone
from rest_framework import serializers

from billing.models import Invoice, InvoiceLine, Payment
from catalog.models import Product
from customers.models import Customer
from tenancy.models import BusinessSettings

AMOUNT = DecimalField(max_digits=28, decimal_places=2)
ZERO = Decimal("0.00")


class AnalyticsFilters(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    currency = serializers.CharField(min_length=3, max_length=3, required=False)
    customer = serializers.UUIDField(required=False)
    document_kind = serializers.ChoiceField(choices=["invoice"], required=False, default="invoice")

    def validate_currency(self, value):
        value = value.upper()
        if pycountry.currencies.get(alpha_3=value) is None:
            raise serializers.ValidationError("Seleccioná una moneda ISO válida.")
        return value


def reporting_context(tenant, params):
    preferences = BusinessSettings.objects.filter(tenant=tenant).first() or BusinessSettings(
        tenant=tenant
    )
    zone = ZoneInfo(preferences.timezone)
    today = timezone.localdate(timezone=zone)
    month = today.year * 12 + today.month - 1 - 11
    defaults = {
        "date_from": today.replace(year=month // 12, month=month % 12 + 1, day=1),
        "date_to": today,
        "currency": preferences.default_currency,
    }
    validator = AnalyticsFilters(data=params)
    validator.is_valid(raise_exception=True)
    values = defaults | validator.validated_data
    if (
        values["date_from"].year < 1900
        or values["date_to"].year > 9998
        or values["date_from"] > values["date_to"]
        or (values["date_to"] - values["date_from"]).days > 3660
    ):
        raise serializers.ValidationError(
            {"date_to": "Elegí un período válido de hasta diez años."}
        )
    return values, zone, today


def amount(value):
    return format(value if value is not None else ZERO, ".2f")


def invoices_with_balances(tenant, currency):
    payments = (
        Payment.objects.filter(tenant=tenant, invoice_id=OuterRef("pk"), reversal__isnull=True)
        .order_by()
        .values("invoice_id")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    query = Invoice.objects.filter(tenant=tenant, status="issued", document_kind="invoice")
    if currency:
        query = query.filter(currency=currency)
    return query.annotate(
        paid_amount=Coalesce(
            Subquery(payments, output_field=AMOUNT), Value(ZERO), output_field=AMOUNT
        ),
    ).annotate(
        current_balance=ExpressionWrapper(F("total") - F("paid_amount"), output_field=AMOUNT)
    )


def boundaries(start, end, zone):
    return datetime.combine(start, time.min, tzinfo=zone), datetime.combine(
        end + timedelta(days=1), time.min, tzinfo=zone
    )


def report_queries(tenant, values, zone):
    start, end = boundaries(values["date_from"], values["date_to"], zone)
    invoices = invoices_with_balances(tenant, values["currency"])
    payments = Payment.objects.filter(
        tenant=tenant,
        invoice__tenant=tenant,
        invoice__status="issued",
        invoice__document_kind="invoice",
        invoice__currency=values["currency"],
        reversal__isnull=True,
    )
    if values.get("customer"):
        invoices = invoices.filter(customer_id=values["customer"])
        payments = payments.filter(invoice__customer_id=values["customer"])
    return invoices.filter(issued_at__gte=start, issued_at__lt=end), payments.filter(
        received_at__gte=start, received_at__lt=end
    )


def period_metrics(invoices, payments, today):
    totals = invoices.aggregate(
        invoiced=Sum("total", default=ZERO),
        count=Count("pk"),
        outstanding=Sum("current_balance", filter=Q(current_balance__gt=0), default=ZERO),
        overdue=Sum(
            "current_balance", filter=Q(current_balance__gt=0, due_date__lt=today), default=ZERO
        ),
        unpaid_count=Count("pk", filter=Q(current_balance__gt=0)),
        unscheduled_count=Count("pk", filter=Q(current_balance__gt=0, due_date__isnull=True)),
        overpaid_count=Count("pk", filter=Q(current_balance__lt=0)),
    )
    collected = payments.aggregate(total=Sum("amount", default=ZERO))["total"]
    return {
        "invoiced": amount(totals["invoiced"]),
        "collected": amount(collected),
        "outstanding": amount(totals["outstanding"]),
        "overdue": amount(totals["overdue"]),
        "issued_count": totals["count"],
        "unpaid_count": totals["unpaid_count"],
        "unscheduled_count": totals["unscheduled_count"],
        "overpaid_count": totals["overpaid_count"],
    }


def overview(tenant, params):
    from .snapshot import reporting_snapshot

    with reporting_snapshot():
        return _overview(tenant, params)


def _overview(tenant, params):
    values, zone, today = reporting_context(tenant, params)
    invoices, payments = report_queries(tenant, values, zone)
    metrics = period_metrics(invoices, payments, today)
    length = (values["date_to"] - values["date_from"]).days + 1
    previous_values = values | {
        "date_to": values["date_from"] - timedelta(days=1),
        "date_from": values["date_from"] - timedelta(days=length),
    }
    previous_invoices, previous_payments = report_queries(tenant, previous_values, zone)
    previous = period_metrics(previous_invoices, previous_payments, today)
    monthly_invoices = {
        row["month"].strftime("%Y-%m"): row["total"]
        for row in invoices.annotate(month=TruncMonth("issued_at", tzinfo=zone))
        .values("month")
        .annotate(total=Sum("total"))
        .order_by("month")
    }
    monthly_payments = {
        row["month"].strftime("%Y-%m"): row["total"]
        for row in payments.annotate(month=TruncMonth("received_at", tzinfo=zone))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    }
    month = values["date_from"].year * 12 + values["date_from"].month - 1
    end_month = values["date_to"].year * 12 + values["date_to"].month - 1
    monthly = []
    while month <= end_month:
        key = f"{month // 12:04}-{month % 12 + 1:02}"
        monthly.append(
            {
                "month": key,
                "invoiced": amount(monthly_invoices.get(key)),
                "collected": amount(monthly_payments.get(key)),
            }
        )
        month += 1
    customers = [
        {
            "id": str(row["customer_id"]),
            "name": row["customer__name"],
            "invoiced": amount(row["total"]),
        }
        for row in invoices.values("customer_id", "customer__name")
        .annotate(total=Sum("total"))
        .order_by("-total", "customer_id")[:10]
    ]
    product_rows = (
        InvoiceLine.objects.filter(invoice__in=invoices.values("pk"))
        .values("product_id", "description_snapshot", "sku_snapshot")
        .annotate(total=Sum("total"), quantity=Sum("quantity"))
        .order_by("-total", "description_snapshot", "product_id")[:10]
    )
    products = [
        {
            "id": str(row["product_id"]) if row["product_id"] else None,
            "name": row["description_snapshot"],
            "sku": row["sku_snapshot"],
            "invoiced": amount(row["total"]),
            "quantity": str(row["quantity"]),
        }
        for row in product_rows
    ]
    methods = [
        {
            "method": row["method"],
            "label": Payment.Method(row["method"]).label,
            "collected": amount(row["total"]),
            "count": row["count"],
        }
        for row in payments.values("method")
        .annotate(total=Sum("amount"), count=Count("pk"))
        .order_by("method")
    ]
    aging = []
    unpaid = invoices.filter(current_balance__gt=0)
    for label, condition in [
        ("not_due", Q(due_date__gte=today)),
        ("1_30", Q(due_date__lt=today, due_date__gte=today - timedelta(days=30))),
        (
            "31_60",
            Q(due_date__lt=today - timedelta(days=30), due_date__gte=today - timedelta(days=60)),
        ),
        (
            "61_90",
            Q(due_date__lt=today - timedelta(days=60), due_date__gte=today - timedelta(days=90)),
        ),
        ("over_90", Q(due_date__lt=today - timedelta(days=90))),
        ("unscheduled", Q(due_date__isnull=True)),
    ]:
        data = unpaid.filter(condition).aggregate(
            total=Sum("current_balance", default=ZERO), count=Count("pk")
        )
        aging.append({"bucket": label, "balance": amount(data["total"]), "count": data["count"]})
    return {
        "company": {"id": str(tenant.pk), "name": tenant.name},
        "filters": {k: str(v) for k, v in values.items()},
        "timezone": str(zone),
        "as_of": str(today),
        "balance_basis": "current",
        "metrics": metrics,
        "previous": {
            "date_from": str(previous_values["date_from"]),
            "date_to": str(previous_values["date_to"]),
            "metrics": previous,
        },
        "monthly": monthly,
        "customers": customers,
        "products": products,
        "payment_methods": methods,
        "aging": aging,
    }


def record_counts(tenant):
    invoices = Invoice.objects.filter(tenant=tenant).aggregate(
        drafts=Count("pk", filter=Q(status="draft")), issued=Count("pk", filter=Q(status="issued"))
    )
    return {
        "customers": Customer.objects.filter(tenant=tenant, is_active=True).count(),
        "products": Product.objects.filter(tenant=tenant, is_active=True).count(),
        **invoices,
    }
