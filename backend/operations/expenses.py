"""Payables are internal records, separate from purchase receipt and bank execution."""

import hashlib
import json
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import (
    BooleanField,
    Case,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from auditlog.models import AuditEvent
from auditlog.services import record_audit_event
from billing.exceptions import IdempotencyConflict
from billing.services import round_money
from tenancy.services import lock_company

from .expense_serializers import CategorySerializer, ExpenseInput, ExpensePaymentInput
from .models import (
    Expense,
    ExpenseCategory,
    ExpensePayment,
    ExpensePaymentReversal,
    PurchaseOrder,
    Supplier,
)
from .serializers import ReversalInput
from .services import request_key

FINANCE_ROLES = {"owner", "admin", "accountant"}


def expense_query(tenant):
    amount = DecimalField(max_digits=16, decimal_places=2)
    payments = (
        ExpensePayment.objects.filter(tenant=tenant, expense=OuterRef("pk"), reversal__isnull=True)
        .order_by()
        .values("expense")
        .annotate(total=Sum("amount"))
        .values("total")
    )

    return (
        Expense.objects.filter(tenant=tenant)
        .defer("attachment")
        .select_related("supplier", "category")
        .annotate(
            paid_amount=Coalesce(
                Subquery(payments, output_field=amount), Value(Decimal("0.00")), output_field=amount
            ),
            has_attachment=Case(
                When(attachment__isnull=False, then=True),
                default=False,
                output_field=BooleanField(),
            ),
        )
        .annotate(balance=ExpressionWrapper(F("total") - F("paid_amount"), output_field=amount))
    )


def validate_purchase_link(expense):
    if expense.purchase_order_id:
        order = PurchaseOrder.objects.filter(
            tenant=expense.tenant, pk=expense.purchase_order_id
        ).first()
        if (
            order is None
            or order.status not in {"ordered", "closed"}
            or order.supplier_id != expense.supplier_id
            or order.currency != expense.currency
        ):
            raise ValidationError(
                {
                    "purchase_order": "El pedido debe estar confirmado y corresponder a la misma empresa, proveedor y moneda."
                }
            )


@transaction.atomic
def save_category(*, tenant_id, actor, data, category_id=None, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor, roles=FINANCE_ROLES)
    category = (
        ExpenseCategory.objects.select_for_update().filter(tenant=tenant, pk=category_id).first()
        if category_id
        else None
    )
    if category_id and category is None:
        raise NotFound()
    serializer = CategorySerializer(category, data=data, partial=bool(category))
    serializer.is_valid(raise_exception=True)
    name = serializer.validated_data.get("name", category.name if category else "")
    if ExpenseCategory.objects.filter(tenant=tenant, name=name).exclude(pk=category_id).exists():
        raise ValidationError({"name": "La categoría ya existe en esta empresa."})
    category = serializer.save(tenant=tenant)
    record_audit_event(
        tenant=tenant,
        actor=actor,
        request=request,
        action=AuditEvent.Action.UPDATE if category_id else AuditEvent.Action.CREATE,
        entity_type="operations.expense_category",
        entity_id=category.pk,
        metadata={"name": category.name, "is_active": category.is_active},
    )
    return category


@transaction.atomic
def save_expense(*, tenant_id, actor, data, expense_id=None, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor, roles=FINANCE_ROLES)
    expense = (
        Expense.objects.select_for_update().filter(tenant=tenant, pk=expense_id).first()
        if expense_id
        else Expense(tenant=tenant, created_by=actor)
    )
    if expense is None:
        raise NotFound()
    if expense.status != "draft":
        raise ValidationError("Solo se puede editar un borrador de gasto.")
    serializer = ExpenseInput(data=data, partial=bool(expense_id))
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    for field, model in [("supplier", Supplier), ("category", ExpenseCategory)]:
        if field in values:
            key = values[field]
            query = model.objects.filter(tenant=tenant, pk=key)
            if key != getattr(expense, f"{field}_id"):
                query = query.filter(is_active=True)
            related = query.first() if key else None
            if key and related is None:
                raise ValidationError({field: "La referencia no está disponible en esta empresa."})
            setattr(expense, field, related)
    for field in [
        "description",
        "reference",
        "incurred_on",
        "due_date",
        "currency",
        "net_amount",
        "tax_rate",
    ]:
        if field in values:
            setattr(expense, field, values[field])
    if "purchase_order" in values:
        expense.purchase_order_id = values["purchase_order"]
    validate_purchase_link(expense)
    if expense.due_date and expense.due_date < expense.incurred_on:
        raise ValidationError(
            {"due_date": "El vencimiento no puede ser anterior a la fecha del gasto."}
        )
    if expense.incurred_on.year < 1900 or expense.incurred_on.year > 9998:
        raise ValidationError({"incurred_on": "La fecha está fuera del rango admitido."})
    if "attachment_data" in values:
        expense.attachment = values["attachment_data"]
    if values.get("remove_attachment"):
        expense.attachment = None
    expense.tax_amount = round_money(expense.net_amount * expense.tax_rate / Decimal("100"))
    expense.total = expense.net_amount + expense.tax_amount
    expense.save()
    record_audit_event(
        tenant=tenant,
        actor=actor,
        request=request,
        action=AuditEvent.Action.UPDATE if expense_id else AuditEvent.Action.CREATE,
        entity_type="operations.expense",
        entity_id=expense.pk,
        metadata={
            "currency": expense.currency,
            "net_amount": str(expense.net_amount),
            "tax_rate": str(expense.tax_rate),
            "total": str(expense.total),
            "attachment_changed": "attachment_data" in values
            or values.get("remove_attachment", False),
            "description_recorded": True,
        },
    )
    return expense


@transaction.atomic
def post_expense(*, tenant_id, actor, expense_id, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor, roles=FINANCE_ROLES)
    expense = Expense.objects.select_for_update().filter(tenant=tenant, pk=expense_id).first()
    if expense is None:
        raise NotFound()
    if expense.status == "posted":
        return expense
    if expense.status != "draft":
        raise ValidationError("El gasto anulado no se registra de nuevo.")
    validate_purchase_link(expense)
    expense.supplier_name_snapshot = expense.supplier.name if expense.supplier_id else ""
    expense.category_name_snapshot = expense.category.name if expense.category_id else ""
    expense.status = "posted"
    expense.posted_by = actor
    expense.posted_at = timezone.now()
    expense.save()
    record_audit_event(
        tenant=tenant,
        actor=actor,
        request=request,
        action=AuditEvent.Action.ISSUE,
        entity_type="operations.expense",
        entity_id=expense.pk,
        metadata={"status": "posted", "total": str(expense.total), "currency": expense.currency},
    )
    return expense


def paid_amount(tenant, expense):
    return ExpensePayment.objects.filter(
        tenant=tenant, expense=expense, reversal__isnull=True
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")


@transaction.atomic
def pay_expense(*, tenant_id, actor, expense_id, data, idempotency_key=None, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor, roles=FINANCE_ROLES)
    expense = Expense.objects.select_for_update().filter(tenant=tenant, pk=expense_id).first()
    if expense is None:
        raise NotFound()
    serializer = ExpensePaymentInput(data=data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    key = request_key(idempotency_key)
    fingerprint = {name: str(value) for name, value in values.items()} | {
        "expense": str(expense.pk)
    }
    digest = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
    previous = ExpensePayment.objects.filter(tenant=tenant, idempotency_key=key).first()
    if previous:
        if previous.request_digest != digest:
            raise IdempotencyConflict(
                "La solicitud corresponde a un pago registrado con otros datos."
            )
        return previous
    if expense.status != "posted":
        raise ValidationError("Registrá el gasto antes de cargar un pago.")
    if values["amount"] > expense.total - paid_amount(tenant, expense):
        raise ValidationError({"amount": "El pago supera el saldo pendiente del gasto."})
    at = values.get("paid_at", timezone.now())
    if at > timezone.now() + timedelta(minutes=5) or at.year < 1900:
        raise ValidationError(
            {"paid_at": "El pago debe tener una fecha registrada válida, sin ser futura."}
        )
    payment = ExpensePayment.objects.create(
        tenant=tenant,
        expense=expense,
        amount=values["amount"],
        method=values["method"],
        reference=values["reference"],
        paid_at=at,
        actor=actor,
        idempotency_key=key,
        request_digest=digest,
    )
    record_audit_event(
        tenant=tenant,
        actor=actor,
        request=request,
        action=AuditEvent.Action.PAYMENT,
        entity_type="operations.expense_payment",
        entity_id=payment.pk,
        metadata={
            "expense": str(expense.pk),
            "amount": str(payment.amount),
            "currency": expense.currency,
            "method": payment.method,
        },
    )
    return payment


@transaction.atomic
def reverse_expense_payment(*, tenant_id, actor, payment_id, data, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor, roles=FINANCE_ROLES)
    payment = (
        ExpensePayment.objects.select_for_update().filter(tenant=tenant, pk=payment_id).first()
    )
    if payment is None:
        raise NotFound()
    serializer = ReversalInput(data=data)
    serializer.is_valid(raise_exception=True)
    existing = ExpensePaymentReversal.objects.filter(tenant=tenant, payment=payment).first()
    if existing:
        return existing
    reversal = ExpensePaymentReversal.objects.create(
        tenant=tenant, payment=payment, actor=actor, reason=serializer.validated_data["reason"]
    )
    record_audit_event(
        tenant=tenant,
        actor=actor,
        request=request,
        action=AuditEvent.Action.SYSTEM,
        entity_type="operations.expense_payment_reversal",
        entity_id=reversal.pk,
        metadata={
            "payment": str(payment.pk),
            "amount": str(payment.amount),
            "reason_recorded": True,
        },
    )
    return reversal


@transaction.atomic
def void_expense(*, tenant_id, actor, expense_id, data, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor, roles=FINANCE_ROLES)
    expense = Expense.objects.select_for_update().filter(tenant=tenant, pk=expense_id).first()
    if expense is None:
        raise NotFound()
    serializer = ReversalInput(data=data)
    serializer.is_valid(raise_exception=True)
    if expense.status == "void":
        return expense
    if paid_amount(tenant, expense) > 0:
        raise ValidationError("Revertí los pagos vigentes antes de anular el gasto.")
    Expense.objects.filter(pk=expense.pk).update(
        status="void", void_reason=serializer.validated_data["reason"], updated_at=timezone.now()
    )
    record_audit_event(
        tenant=tenant,
        actor=actor,
        request=request,
        action=AuditEvent.Action.DEACTIVATE,
        entity_type="operations.expense",
        entity_id=expense.pk,
        metadata={"status": "void", "reason_recorded": True},
    )
    expense.refresh_from_db()
    return expense
