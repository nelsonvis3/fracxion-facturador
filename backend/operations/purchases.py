"""Purchasing commitments and physical receipts, independent from payables/payments."""

import hashlib
import json
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from auditlog.models import AuditEvent
from auditlog.services import record_audit_event
from billing.exceptions import IdempotencyConflict
from billing.services import round_money
from catalog.models import Product
from tenancy.services import lock_company

from .models import (
    InventoryPolicy,
    PurchaseLine,
    PurchaseOrder,
    PurchaseReceipt,
    PurchaseReceiptLine,
    PurchaseReceiptReversal,
    Supplier,
)
from .purchase_serializers import PurchaseInput, ReceiptInput
from .serializers import ReversalInput
from .services import move_stock, request_key

READ_ROLES = {"owner", "admin", "accountant"}
MAX_MONEY = Decimal("99999999999999.99")


def purchase_lines(order):
    quantity = DecimalField(max_digits=12, decimal_places=3)
    return (
        PurchaseLine.objects.filter(order=order)
        .annotate(
            received_quantity=Coalesce(
                Sum(
                    "receipt_lines__quantity",
                    filter=Q(receipt_lines__receipt__reversal__isnull=True),
                ),
                Value(Decimal("0.000")),
                output_field=quantity,
            )
        )
        .annotate(
            remaining_quantity=ExpressionWrapper(
                F("quantity") - F("received_quantity"), output_field=quantity
            )
        )
    )


def audit(tenant, actor, request, entity, action, **metadata):
    record_audit_event(
        tenant=tenant,
        actor=actor,
        request=request,
        action=action,
        entity_type=entity._meta.label_lower,
        entity_id=entity.pk,
        metadata=metadata,
    )


@transaction.atomic
def save_purchase(*, tenant_id, actor, data, order_id=None, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor)
    order = (
        PurchaseOrder.objects.select_for_update().filter(tenant=tenant, pk=order_id).first()
        if order_id
        else PurchaseOrder(tenant=tenant, created_by=actor)
    )
    if order is None:
        raise NotFound()
    if order.status != "draft":
        raise ValidationError("Solo se puede editar un borrador de pedido.")
    serializer = PurchaseInput(data=data, partial=bool(order_id))
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    if "supplier" in values:
        supplier = Supplier.objects.filter(tenant=tenant, pk=values["supplier"]).first()
        if supplier is None or (not supplier.is_active and supplier.pk != order.supplier_id):
            raise ValidationError({"supplier": "El proveedor no está disponible en esta empresa."})
        order.supplier = supplier
    for field in ["currency", "reference", "notes", "expected_on"]:
        if field in values:
            setattr(order, field, values[field])
    if order.expected_on and not 1900 <= order.expected_on.year <= 9998:
        raise ValidationError({"expected_on": "La fecha está fuera del rango admitido."})
    # Replace only draft lines; no receipt can exist before confirmation.
    if "lines" in values:
        product_ids = [line["product"] for line in values["lines"]]
        products = {
            p.pk: p
            for p in Product.objects.filter(tenant=tenant, pk__in=product_ids, is_active=True)
        }
        lines = []
        for position, value in enumerate(values["lines"], 1):
            product = products.get(value["product"])
            if product is None:
                raise ValidationError(
                    {"lines": "Uno de los productos no está disponible en esta empresa."}
                )
            net = round_money(value["quantity"] * value["unit_cost"])
            tax = round_money(net * value["tax_rate"] / Decimal("100"))
            if net + tax > MAX_MONEY:
                raise ValidationError(
                    {"lines": "El importe de una línea supera el límite admitido."}
                )
            lines.append(
                PurchaseLine(
                    order=order,
                    position=position,
                    product=product,
                    product_name_snapshot=product.name,
                    product_type_snapshot=product.product_type,
                    unit_snapshot=product.unit,
                    quantity=value["quantity"],
                    unit_cost=value["unit_cost"],
                    tax_rate=value["tax_rate"],
                    net_amount=net,
                    tax_amount=tax,
                    total=net + tax,
                )
            )
        order.net_amount = sum((line.net_amount for line in lines), Decimal("0.00"))
        order.tax_amount = sum((line.tax_amount for line in lines), Decimal("0.00"))
        order.total = order.net_amount + order.tax_amount
        if order.total > MAX_MONEY:
            raise ValidationError({"lines": "El total supera el límite admitido."})
        order.save()
        order.lines.all().delete()
        PurchaseLine.objects.bulk_create(lines)
    else:
        order.save()
    audit(
        tenant,
        actor,
        request,
        order,
        AuditEvent.Action.UPDATE if order_id else AuditEvent.Action.CREATE,
        currency=order.currency,
        total=str(order.total),
        status=order.status,
    )
    return order


@transaction.atomic
def confirm_purchase(*, tenant_id, actor, order_id, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor)
    order = PurchaseOrder.objects.select_for_update().filter(tenant=tenant, pk=order_id).first()
    if order is None:
        raise NotFound()
    if order.status == "ordered":
        return order
    if order.status != "draft":
        raise ValidationError("Este pedido ya está cerrado.")
    if not order.supplier.is_active:
        raise ValidationError({"supplier": "El proveedor está desactivado."})
    lines = list(order.lines.select_related("product"))
    if not lines:
        raise ValidationError("Agregá al menos una línea.")
    for line in lines:
        product = line.product
        if (
            not product.is_active
            or product.product_type != line.product_type_snapshot
            or product.unit != line.unit_snapshot
        ):
            raise ValidationError(
                {"lines": "El catálogo cambió. Revisá y guardá las líneas antes de confirmar."}
            )
        # Confirmation freezes descriptive data; prices are negotiated explicitly.
        PurchaseLine.objects.filter(pk=line.pk).update(product_name_snapshot=product.name)
    order.supplier_name_snapshot = order.supplier.name
    order.confirmed_at = timezone.now()
    order.status = "ordered"
    order.save()
    audit(
        tenant,
        actor,
        request,
        order,
        AuditEvent.Action.ISSUE,
        total=str(order.total),
        currency=order.currency,
    )
    return order


@transaction.atomic
def receive_purchase(*, tenant_id, actor, order_id, data, idempotency_key=None, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor)
    order = PurchaseOrder.objects.select_for_update().filter(tenant=tenant, pk=order_id).first()
    if order is None:
        raise NotFound()
    serializer = ReceiptInput(data=data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    ids = [value["line"] for value in values["lines"]]
    if len(set(ids)) != len(ids):
        raise ValidationError({"lines": "Cada línea debe aparecer una sola vez por recepción."})
    key = request_key(idempotency_key)
    canonical = {
        "order": str(order.pk),
        "reference": values["reference"],
        "lines": sorted(
            [(str(value["line"]), str(value["quantity"])) for value in values["lines"]]
        ),
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    previous = PurchaseReceipt.objects.filter(tenant=tenant, idempotency_key=key).first()
    if previous:
        if previous.request_digest != digest:
            raise IdempotencyConflict("La solicitud corresponde a otra recepción.")
        return previous
    if order.status != "ordered":
        raise ValidationError("El pedido debe estar confirmado y abierto para recibirlo.")
    lines = {line.pk: line for line in purchase_lines(order).select_related("product")}
    receipt = PurchaseReceipt.objects.create(
        tenant=tenant,
        order=order,
        actor=actor,
        reference=values["reference"],
        idempotency_key=key,
        request_digest=digest,
    )
    for value in values["lines"]:
        line = lines.get(value["line"])
        if line is None or value["quantity"] > line.remaining_quantity:
            raise ValidationError(
                {"lines": "Las cantidades deben corresponder al saldo de este pedido."}
            )
        product = line.product
        if (
            not product.is_active
            or product.product_type != line.product_type_snapshot
            or product.unit != line.unit_snapshot
        ):
            raise ValidationError(
                {"lines": "El producto cambió o está desactivado. Revisá el catálogo."}
            )
        movement = None
        if line.product_type_snapshot == "product":
            if not InventoryPolicy.objects.filter(
                tenant=tenant, product=product, tracking=True
            ).exists():
                raise ValidationError(
                    {
                        "lines": "Habilitá el seguimiento de stock de los productos físicos antes de recibirlos."
                    }
                )
            movement = move_stock(
                tenant_id=tenant.pk,
                actor=actor,
                data={
                    "product": product.pk,
                    "kind": "in",
                    "quantity": value["quantity"],
                    "reason": "Recepción de pedido de compra",
                    "reference": values["reference"],
                },
                idempotency_key=f"purchase_{receipt.pk.hex}_{line.pk.hex}",
                request=request,
            )
        PurchaseReceiptLine.objects.create(
            receipt=receipt, line=line, quantity=value["quantity"], movement=movement
        )
    audit(
        tenant,
        actor,
        request,
        receipt,
        AuditEvent.Action.CREATE,
        order=str(order.pk),
        line_count=len(ids),
    )
    return receipt


@transaction.atomic
def reverse_receipt(*, tenant_id, actor, receipt_id, data, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor)
    receipt = (
        PurchaseReceipt.objects.select_for_update().filter(tenant=tenant, pk=receipt_id).first()
    )
    if receipt is None:
        raise NotFound()
    serializer = ReversalInput(data=data)
    serializer.is_valid(raise_exception=True)
    existing = PurchaseReceiptReversal.objects.filter(receipt=receipt, tenant=tenant).first()
    if existing:
        return existing
    if receipt.order.status != "ordered":
        raise ValidationError(
            "El pedido cerrado conserva sus recepciones. Registrá una devolución de stock independiente."
        )
    for line in receipt.lines.select_related("movement").order_by("line__product_id", "pk"):
        if line.movement_id:
            move_stock(
                tenant_id=tenant.pk,
                actor=actor,
                data=serializer.validated_data,
                reverse_id=line.movement_id,
                idempotency_key=f"purchase_reverse_{receipt.pk.hex}_{line.pk.hex}",
                _receipt_id=receipt.pk,
                request=request,
            )
    reversal = PurchaseReceiptReversal.objects.create(
        tenant=tenant, receipt=receipt, actor=actor, reason=serializer.validated_data["reason"]
    )
    audit(
        tenant,
        actor,
        request,
        reversal,
        AuditEvent.Action.SYSTEM,
        receipt=str(receipt.pk),
        order=str(receipt.order_id),
        reason_recorded=True,
    )
    return reversal


@transaction.atomic
def close_purchase(*, tenant_id, actor, order_id, data, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor)
    order = PurchaseOrder.objects.select_for_update().filter(tenant=tenant, pk=order_id).first()
    if order is None:
        raise NotFound()
    serializer = ReversalInput(data=data)
    serializer.is_valid(raise_exception=True)
    if order.status in {"closed", "cancelled"}:
        return order
    has_received = order.receipts.filter(reversal__isnull=True).exists()
    status = "closed" if has_received else "cancelled"
    PurchaseOrder.objects.filter(pk=order.pk).update(
        status=status,
        closed_at=timezone.now(),
        updated_at=timezone.now(),
        close_reason=serializer.validated_data["reason"],
    )
    audit(
        tenant,
        actor,
        request,
        order,
        AuditEvent.Action.DEACTIVATE,
        status=status,
        reason_recorded=True,
    )
    order.refresh_from_db()
    return order
