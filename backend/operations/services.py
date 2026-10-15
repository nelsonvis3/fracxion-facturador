import hashlib
import json
import re
import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import NotFound, ValidationError

from auditlog.models import AuditEvent
from auditlog.services import record_audit_event
from automation.services import notify
from billing.exceptions import IdempotencyConflict
from catalog.models import Product
from tenancy.models import Membership
from tenancy.services import lock_company

from .models import InventoryMovement, InventoryPolicy, Supplier
from .serializers import InventoryInput, InventoryPolicyInput, ReversalInput, SupplierSerializer


@transaction.atomic
def save_supplier(*, tenant_id, actor, data, supplier_id=None, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor)
    supplier = (
        Supplier.objects.select_for_update().filter(tenant=tenant, pk=supplier_id).first()
        if supplier_id
        else None
    )
    if supplier_id and supplier is None:
        raise NotFound()
    serializer = SupplierSerializer(supplier, data=data, partial=bool(supplier_id))
    serializer.is_valid(raise_exception=True)
    tax_id = serializer.validated_data.get("tax_id", supplier.tax_id if supplier else "")
    if (
        tax_id
        and Supplier.objects.filter(tenant=tenant, tax_id=tax_id).exclude(pk=supplier_id).exists()
    ):
        raise ValidationError(
            {"tax_id": "Ya hay un proveedor con esa identificación en esta empresa."}
        )
    before = (
        {key: getattr(supplier, key) for key in serializer.validated_data if key != "notes"}
        if supplier
        else {}
    )
    supplier = serializer.save(tenant=tenant)
    record_audit_event(
        tenant=tenant,
        actor=actor,
        request=request,
        action=AuditEvent.Action.UPDATE if supplier_id else AuditEvent.Action.CREATE,
        entity_type="operations.supplier",
        entity_id=supplier.pk,
        changes={
            "fields": {
                key: {"before": before.get(key), "after": getattr(supplier, key)}
                for key in serializer.validated_data
                if key != "notes"
            }
        },
        metadata={"notes_changed": "notes" in serializer.validated_data},
    )
    return supplier


def stock_balance(tenant, product):
    return InventoryMovement.objects.filter(tenant=tenant, product=product).aggregate(
        total=Sum("delta")
    )["total"] or Decimal("0.000")


@transaction.atomic
def set_inventory_policy(*, tenant_id, actor, product_id, data, request=None):
    tenant, _ = lock_company(tenant_id, actor=actor)
    product = (
        Product.objects.select_for_update()
        .filter(tenant=tenant, pk=product_id, product_type="product")
        .first()
    )
    if product is None:
        raise NotFound()
    serializer = InventoryPolicyInput(data=data)
    serializer.is_valid(raise_exception=True)
    policy = InventoryPolicy.objects.filter(
        tenant=tenant, product=product
    ).first() or InventoryPolicy(tenant=tenant, product=product)
    for key, value in serializer.validated_data.items():
        setattr(policy, key, value)
    if not policy.tracking and stock_balance(tenant, product) != 0:
        raise ValidationError(
            {"tracking": "El stock debe ser cero antes de desactivar el seguimiento."}
        )
    policy.save()
    record_audit_event(
        tenant=tenant,
        actor=actor,
        request=request,
        action=AuditEvent.Action.UPDATE,
        entity_type="operations.inventory_policy",
        entity_id=product.pk,
        metadata={"tracking": policy.tracking, "minimum": str(policy.minimum)},
    )
    return policy


def request_key(key):
    key = key or str(uuid.uuid4())
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key):
        raise ValidationError("La solicitud tiene un identificador inválido.")
    return key


@transaction.atomic
def move_stock(
    *, tenant_id, actor, data, idempotency_key=None, reverse_id=None, request=None, _receipt_id=None
):
    tenant, _ = lock_company(tenant_id, actor=actor)
    serializer = ReversalInput(data=data) if reverse_id else InventoryInput(data=data)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    original = (
        InventoryMovement.objects.filter(tenant=tenant, pk=reverse_id).first()
        if reverse_id
        else None
    )
    if reverse_id and original is None:
        raise NotFound()
    if original:
        from .models import PurchaseReceiptLine

        source = PurchaseReceiptLine.objects.filter(movement=original).first()
        if source is not None and source.receipt_id != _receipt_id:
            raise ValidationError(
                "Revertí la recepción desde Compras para conservar sus cantidades y stock coherentes."
            )
    product_id = original.product_id if original else values["product"]
    key = request_key(idempotency_key)
    canonical = {key: str(value) for key, value in values.items()} | {
        "reverse_id": str(reverse_id or "")
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    previous = InventoryMovement.objects.filter(tenant=tenant, idempotency_key=key).first()
    if previous:
        if previous.request_digest != digest:
            raise IdempotencyConflict("Esta solicitud ya corresponde a otro movimiento.")
        return previous
    product = (
        Product.objects.select_for_update()
        .filter(tenant=tenant, pk=product_id, product_type="product")
        .first()
    )
    if product is None:
        raise ValidationError({"product": "El producto no está disponible en esta empresa."})
    policy = InventoryPolicy.objects.filter(tenant=tenant, product=product, tracking=True).first()
    if policy is None:
        raise ValidationError(
            {"product": "Habilitá el seguimiento de este producto antes de registrar movimientos."}
        )
    if original:
        if (
            original.reverses_id
            or InventoryMovement.objects.filter(tenant=tenant, reverses=original).exists()
        ):
            raise ValidationError("Este movimiento ya está revertido o es una reversión.")
        delta = -original.delta
        kind = "reversal"
        reference = original.reference
    else:
        kind = values["kind"]
        quantity = values["quantity"]
        if quantity == 0 or (kind != "adjustment" and quantity < 0):
            raise ValidationError(
                {
                    "quantity": "Ingresá una cantidad positiva; los ajustes admiten signos y nunca cero."
                }
            )
        if kind == "in" and not product.is_active:
            raise ValidationError(
                {"product": "No se permiten entradas de un producto desactivado."}
            )
        delta = -quantity if kind == "out" else quantity
        reference = values["reference"]
    balance = stock_balance(tenant, product) + delta
    if balance < 0:
        raise ValidationError({"quantity": "El movimiento dejaría stock negativo."})
    if balance > Decimal("999999999.999"):
        raise ValidationError({"quantity": "El saldo supera la capacidad admitida."})
    movement = InventoryMovement.objects.create(
        tenant=tenant,
        product=product,
        kind=kind,
        delta=delta,
        balance_after=balance,
        reason=values["reason"],
        reference=reference,
        product_name_snapshot=product.name,
        unit_snapshot=product.unit,
        actor=actor,
        reverses=original,
        idempotency_key=key,
        request_digest=digest,
    )
    record_audit_event(
        tenant=tenant,
        actor=actor,
        request=request,
        action=AuditEvent.Action.CREATE,
        entity_type="operations.inventory_movement",
        entity_id=movement.pk,
        metadata={
            "product": str(product.pk),
            "kind": kind,
            "delta": str(delta),
            "balance_after": str(balance),
            "reverses": str(reverse_id or ""),
            "reason_recorded": True,
        },
    )
    if balance <= policy.minimum:
        for member in Membership.objects.filter(
            tenant=tenant, is_active=True, user__is_active=True, role__in=["owner", "admin"]
        ).select_related("user"):
            notify(
                tenant=tenant,
                recipient=member.user,
                key=f"stock:{movement.pk}",
                title="Stock bajo",
                message=f"{product.name}: {balance:.3f} {product.unit}. Umbral: {policy.minimum:.3f}.",
            )
    return movement
