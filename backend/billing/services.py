import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import pycountry
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from auditlog.models import AuditEvent
from auditlog.services import record_audit_event
from catalog.models import Product
from customers.models import Customer
from tenancy.models import Membership, Tenant

from .exceptions import IdempotencyConflict
from .models import (
    Invoice,
    InvoiceLine,
    Payment,
    PaymentReversal,
)

MONEY_QUANTUM = Decimal("0.01")
PRICE_QUANTUM = Decimal("0.0001")
MAX_INVOICE_LINES = 100
MAX_MONEY = Decimal("99999999999999.99")
MAX_QUANTITY = Decimal("999999999.999")
ADMIN_ROLES = frozenset({Membership.Role.OWNER, Membership.Role.ADMIN})
UNSET = object()


def round_money(amount: Decimal) -> Decimal:
    """Redondea un importe a dos decimales."""
    return amount.quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


@transaction.atomic
def create_invoice_draft(
    *,
    tenant,
    customer_id,
    currency: str,
    lines: list[dict],
    actor,
    notes: str = "",
    request=None,
    due_date=UNSET,
    payment_terms_days=UNSET,
) -> Invoice:
    """
    Crea un borrador de factura interna y sus líneas.

    El cliente y los productos se vuelven a comprobar dentro
    de la transacción. Los precios e impuestos se obtienen
    exclusivamente del catálogo.

    Si falla cualquier escritura, incluida la auditoría,
    se revierte la operación completa.
    """

    locked_tenant = Tenant.objects.select_for_update().filter(pk=tenant.pk, is_active=True).first()
    if locked_tenant is None:
        raise ValidationError({"tenant": "La empresa no está activa."})

    tenant = locked_tenant
    _require_payment_role(tenant=tenant, actor=actor, allowed_roles=ADMIN_ROLES)

    if not isinstance(notes, str) or len(notes) > 10000:
        raise ValidationError({"notes": "Las notas admiten hasta 10000 caracteres."})

    if not lines:
        raise ValidationError({"lines": "La factura debe contener al menos una línea."})

    if len(lines) > MAX_INVOICE_LINES:
        raise ValidationError(
            {"lines": (f"La factura admite como máximo {MAX_INVOICE_LINES} líneas.")}
        )

    currency = currency.strip().upper()
    if pycountry.currencies.get(alpha_3=currency) is None:
        raise ValidationError({"currency": "Seleccioná una moneda ISO reconocida."})

    # Bloqueamos el cliente para que su estado no cambie
    # concurrentemente durante la creación del borrador.
    customer = (
        Customer.objects.select_for_update()
        .filter(
            pk=customer_id,
            tenant=tenant,
            is_active=True,
        )
        .first()
    )

    if customer is None:
        raise ValidationError(
            {"customer": ("El cliente no existe, está inactivo o no pertenece a esta empresa.")}
        )

    product_ids = {line["product"] for line in lines}

    # Bloqueamos los productos en un orden estable.
    products = (
        Product.objects.select_for_update()
        .filter(
            pk__in=product_ids,
            tenant=tenant,
            is_active=True,
        )
        .order_by("pk")
    )

    products_by_id = {product.pk: product for product in products}

    if len(products_by_id) != len(product_ids):
        raise ValidationError(
            {
                "lines": (
                    "Uno o más productos no existen, están inactivos "
                    "o no pertenecen a esta empresa."
                )
            }
        )

    if any(product.currency != currency for product in products_by_id.values()):
        raise ValidationError(
            {"currency": ("La moneda debe coincidir con la de todos los productos.")}
        )

    from tenancy.models import BusinessSettings

    preferences = BusinessSettings.objects.filter(tenant=tenant).first() or BusinessSettings(
        tenant=tenant
    )
    if payment_terms_days is UNSET:
        payment_terms_days = preferences.payment_terms_days
    if payment_terms_days is not None and (
        isinstance(payment_terms_days, bool)
        or not isinstance(payment_terms_days, int)
        or not 0 <= payment_terms_days <= 3650
    ):
        raise ValidationError({"payment_terms_days": "Los plazos admiten entre 0 y 3650 días."})
    if due_date is UNSET:
        due_date = (
            timezone.localdate(timezone=ZoneInfo(preferences.timezone))
            + timedelta(days=payment_terms_days)
            if payment_terms_days is not None
            else None
        )
    if due_date is not None and (
        not isinstance(due_date, date) or isinstance(due_date, type(timezone.now()))
    ):
        raise ValidationError({"due_date": "El vencimiento debe ser una fecha válida."})
    # Snapshot issuer settings as well; changes never rewrite issued documents.
    issuer_snapshot = {
        "name": tenant.name,
        "legal_name": tenant.legal_name,
        "tax_id": tenant.tax_id,
        "country_code": preferences.country_code,
        "address": preferences.address,
        "contact_email": preferences.contact_email,
        "contact_phone": preferences.contact_phone,
    }
    invoice = Invoice.objects.create(
        tenant=tenant,
        customer=customer,
        created_by=actor,
        document_kind=Invoice.DocumentKind.INVOICE,
        status=Invoice.Status.DRAFT,
        currency=currency,
        customer_name_snapshot=customer.name,
        customer_legal_name_snapshot=customer.legal_name,
        customer_document_type_snapshot=customer.document_type,
        customer_document_number_snapshot=(customer.document_number or ""),
        customer_address_snapshot=customer.address,
        customer_city_snapshot=customer.city,
        customer_province_snapshot=customer.province,
        customer_email_snapshot=customer.email,
        customer_country_code_snapshot=customer.country_code,
        customer_postal_code_snapshot=customer.postal_code,
        notes=notes,
        due_date=due_date,
        payment_terms_days=payment_terms_days,
        issuer_snapshot=issuer_snapshot,
        footer_snapshot=preferences.invoice_footer,
    )

    subtotal_total = Decimal("0.00")
    tax_total = Decimal("0.00")

    # Crear cada línea con precios tomados del catálogo.
    for position, line_data in enumerate(lines, start=1):
        product = products_by_id[line_data["product"]]
        quantity = line_data["quantity"]
        try:
            quantity = Decimal(str(quantity))
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError({"lines": "La cantidad no es válida."})
        if not quantity.is_finite() or quantity <= 0 or quantity > MAX_QUANTITY:
            raise ValidationError({"lines": "La cantidad debe ser mayor que cero."})
        if quantity != quantity.quantize(Decimal("0.001")):
            raise ValidationError({"lines": "La cantidad admite hasta tres decimales."})

        unit_price = product.unit_price.quantize(
            PRICE_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

        # Primero redondeamos el subtotal de la línea a centavos.
        line_subtotal = round_money(quantity * unit_price)

        # Calculamos el impuesto sobre el subtotal redondeado.
        line_tax = round_money(line_subtotal * product.tax_rate / Decimal("100"))

        line_total = line_subtotal + line_tax
        if max(line_subtotal, line_tax, line_total) > MAX_MONEY:
            raise ValidationError({"lines": "El importe de una línea excede el máximo permitido."})

        InvoiceLine.objects.create(
            invoice=invoice,
            product=product,
            position=position,
            description_snapshot=product.name,
            sku_snapshot=product.sku or "",
            unit_snapshot=product.unit,
            quantity=quantity,
            unit_price=unit_price,
            tax_rate=product.tax_rate,
            subtotal=line_subtotal,
            tax_amount=line_tax,
            total=line_total,
        )

        subtotal_total += line_subtotal
        tax_total += line_tax
        if subtotal_total + tax_total > MAX_MONEY:
            raise ValidationError({"total": "El total excede el máximo permitido."})

    invoice.subtotal = round_money(subtotal_total)
    invoice.tax_total = round_money(tax_total)
    invoice.total = round_money(invoice.subtotal + invoice.tax_total)

    invoice.save(
        update_fields=[
            "subtotal",
            "tax_total",
            "total",
            "updated_at",
        ]
    )

    # La auditoría registra los datos necesarios sin copiar
    # las notas libres ni los datos completos del cliente.
    record_audit_event(
        action=AuditEvent.Action.CREATE,
        entity_type="billing.invoice",
        entity_id=str(invoice.pk),
        tenant=tenant,
        actor=actor,
        changes={
            "fields": {
                "status": {
                    "before": None,
                    "after": invoice.status,
                },
                "currency": {
                    "before": None,
                    "after": invoice.currency,
                },
                "subtotal": {
                    "before": None,
                    "after": str(invoice.subtotal),
                },
                "tax_total": {
                    "before": None,
                    "after": str(invoice.tax_total),
                },
                "total": {
                    "before": None,
                    "after": str(invoice.total),
                },
            },
        },
        metadata={
            "line_count": len(lines),
        },
        request=request,
    )

    return invoice


@transaction.atomic
def issue_invoice(
    *,
    tenant,
    invoice_id,
    actor,
    request=None,
) -> Invoice:
    """
    Emite una factura interna de forma transaccional.

    La numeración se calcula por empresa bajo bloqueo de la fila
    Tenant. Todas las operaciones de emisión deben pasar por este
    servicio para mantener la secuencia segura ante concurrencia.

    Si falla la validación o la auditoría, la transacción se revierte.
    """

    # Bloquear la empresa serializa las emisiones de ese tenant.
    locked_tenant = (
        Tenant.objects.select_for_update()
        .filter(
            pk=tenant.pk,
            is_active=True,
        )
        .first()
    )

    if locked_tenant is None:
        raise ValidationError({"tenant": "La empresa no existe o no está activa."})

    # Comprobar que el actor siga activo en la base de datos.
    user_model = get_user_model()

    actor_is_active = user_model.objects.filter(
        pk=getattr(actor, "pk", None),
        is_active=True,
    ).exists()

    if not getattr(actor, "is_authenticated", False) or not actor_is_active:
        raise PermissionDenied("Se requiere un usuario autenticado y activo.")

    # Volver a comprobar los permisos dentro de la transacción.
    membership = (
        Membership.objects.select_for_update()
        .filter(
            tenant=locked_tenant,
            user_id=actor.pk,
            is_active=True,
            role__in=[
                Membership.Role.OWNER,
                Membership.Role.ADMIN,
            ],
        )
        .first()
    )

    if membership is None:
        raise PermissionDenied("No tenés permisos para emitir facturas en esta empresa.")

    # Bloquear el documento e impedir que se emita desde otra empresa.
    invoice = (
        Invoice.objects.select_for_update()
        .filter(
            pk=invoice_id,
            tenant=locked_tenant,
        )
        .first()
    )

    if invoice is None:
        raise ValidationError({"invoice": "La factura no existe en esta empresa."})

    if invoice.status != Invoice.Status.DRAFT:
        raise ValidationError({"status": "Solo se pueden emitir facturas en borrador."})

    # Todavía no permitimos emitir notas de crédito ni de débito:
    # requieren reglas de negocio y referencias documentales propias.
    if invoice.document_kind != Invoice.DocumentKind.INVOICE:
        raise ValidationError(
            {
                "document_kind": (
                    "Este servicio solo admite facturas internas. "
                    "Las notas de crédito y débito requieren otro flujo."
                )
            }
        )

    lines = list(
        InvoiceLine.objects.select_for_update().filter(invoice=invoice).order_by("position")
    )

    if not lines:
        raise ValidationError({"lines": "No se puede emitir una factura sin líneas."})

    if invoice.customer.tenant_id != locked_tenant.pk:
        raise ValidationError({"customer": "El cliente no pertenece a esta empresa."})

    subtotal_sum = Decimal("0.00")
    tax_sum = Decimal("0.00")

    # Verificar nuevamente la consistencia de cada línea antes
    # de asignar una numeración definitiva.
    product_ids = {line.product_id for line in lines if line.product_id is not None}
    authorized_products = set(
        Product.objects.filter(pk__in=product_ids, tenant=locked_tenant).values_list(
            "pk", flat=True
        )
    )
    if product_ids != authorized_products:
        raise ValidationError({"lines": "Una línea contiene un producto asociado a otra empresa."})
    for line in lines:
        expected_subtotal = round_money(line.quantity * line.unit_price)

        expected_tax = round_money(expected_subtotal * line.tax_rate / Decimal("100"))

        expected_total = expected_subtotal + expected_tax

        if (
            line.subtotal != expected_subtotal
            or line.tax_amount != expected_tax
            or line.total != expected_total
        ):
            raise ValidationError(
                {"lines": ("Una o más líneas contienen importes inconsistentes.")}
            )

        subtotal_sum += expected_subtotal
        tax_sum += expected_tax

    subtotal_sum = round_money(subtotal_sum)
    tax_sum = round_money(tax_sum)
    total_sum = subtotal_sum + tax_sum

    if (
        invoice.subtotal != subtotal_sum
        or invoice.tax_total != tax_sum
        or invoice.total != total_sum
    ):
        raise ValidationError(
            {"total": ("Los totales de la factura no coinciden con los importes de sus líneas.")}
        )

    # El bloqueo de Tenant hace que las emisiones de una misma
    # empresa se ejecuten secuencialmente. La restricción única
    # de PostgreSQL constituye una segunda barrera.
    last_number = (
        Invoice.objects.filter(tenant=locked_tenant).aggregate(max_number=Max("internal_number"))[
            "max_number"
        ]
        or 0
    )

    next_number = last_number + 1
    issued_at = timezone.now()

    old_status = invoice.status

    invoice.internal_number = next_number
    invoice.status = Invoice.Status.ISSUED
    invoice.issued_at = issued_at
    invoice.issued_by = actor

    invoice.save(
        update_fields=[
            "internal_number",
            "status",
            "issued_at",
            "issued_by",
            "updated_at",
        ]
    )

    # El evento forma parte de la misma transacción que la emisión.
    record_audit_event(
        action=AuditEvent.Action.ISSUE,
        entity_type="billing.invoice",
        entity_id=str(invoice.pk),
        tenant=locked_tenant,
        actor=actor,
        changes={
            "fields": {
                "status": {
                    "before": old_status,
                    "after": invoice.status,
                },
                "internal_number": {
                    "before": None,
                    "after": invoice.internal_number,
                },
                "issued_at": {
                    "before": None,
                    "after": issued_at.isoformat(),
                },
                "total": {
                    "before": str(invoice.total),
                    "after": str(total_sum),
                },
            }
        },
        metadata={
            "numbering_type": "internal",
            "line_count": len(lines),
        },
        request=request,
    )

    return invoice


PAYMENT_ROLES = frozenset(
    {
        Membership.Role.OWNER,
        Membership.Role.ADMIN,
        Membership.Role.ACCOUNTANT,
    }
)

REVERSAL_ROLES = frozenset(
    {
        Membership.Role.OWNER,
        Membership.Role.ADMIN,
    }
)


def _require_payment_role(*, tenant, actor, allowed_roles):
    """Comprueba que el usuario siga activo y tenga el rol requerido."""

    if not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Se requiere un usuario autenticado.")

    user_model = get_user_model()

    if not user_model.objects.filter(
        pk=actor.pk,
        is_active=True,
    ).exists():
        raise PermissionDenied("El usuario no está activo.")

    membership = (
        Membership.objects.select_for_update()
        .filter(
            tenant=tenant,
            user_id=actor.pk,
            is_active=True,
            role__in=allowed_roles,
        )
        .first()
    )

    if membership is None:
        raise PermissionDenied("No tenés permisos para realizar esta operación.")

    return membership


def get_invoice_balance(invoice):
    """
    Calcula el saldo pendiente.

    Los pagos con una reversión registrada no cuentan como
    pagos efectivos.
    """
    paid_total = Payment.objects.filter(
        tenant=invoice.tenant,
        invoice=invoice,
        reversal__isnull=True,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    return round_money(invoice.total - paid_total)


@transaction.atomic
def record_payment(
    *,
    tenant,
    invoice_id,
    actor,
    method,
    amount,
    external_reference=None,
    received_at=None,
    notes="",
    request=None,
    idempotency_key=None,
) -> Payment:
    """
    Registra un pago parcial o total.

    Bloquea la empresa y la factura, verifica el saldo pendiente
    y registra el evento de auditoría en la misma transacción.
    """

    locked_tenant = (
        Tenant.objects.select_for_update()
        .filter(
            pk=tenant.pk,
            is_active=True,
        )
        .first()
    )

    if locked_tenant is None:
        raise ValidationError({"tenant": "La empresa no existe o no está activa."})

    _require_payment_role(
        tenant=locked_tenant,
        actor=actor,
        allowed_roles=PAYMENT_ROLES,
    )

    invoice = (
        Invoice.objects.select_for_update()
        .filter(
            pk=invoice_id,
            tenant=locked_tenant,
        )
        .first()
    )

    if invoice is None:
        raise ValidationError({"invoice": "La factura no existe en esta empresa."})

    if invoice.status != Invoice.Status.ISSUED:
        raise ValidationError({"invoice": "Solo se aceptan pagos de facturas emitidas."})

    try:
        payment_amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({"amount": "El importe no es válido."})

    if not payment_amount.is_finite() or payment_amount <= 0:
        raise ValidationError({"amount": "El importe debe ser positivo y finito."})

    try:
        rounded_amount = payment_amount.quantize(
            MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
    except InvalidOperation:
        raise ValidationError({"amount": "El importe no es válido."})

    if rounded_amount != payment_amount:
        raise ValidationError({"amount": "El importe debe tener como máximo dos decimales."})

    payment_amount = rounded_amount
    if payment_amount > MAX_MONEY:
        raise ValidationError({"amount": "El importe excede el máximo permitido."})
    if method not in Payment.Method.values:
        raise ValidationError({"method": "Seleccioná un método de pago válido."})
    if external_reference is not None and not isinstance(external_reference, str):
        raise ValidationError({"external_reference": "La referencia debe ser texto."})

    external_reference = external_reference.strip() if external_reference else None
    external_reference = external_reference or None
    if external_reference and len(external_reference) > 120:
        raise ValidationError({"external_reference": "La referencia admite hasta 120 caracteres."})

    if received_at is not None and (
        not isinstance(received_at, datetime) or not timezone.is_aware(received_at)
    ):
        raise ValidationError({"received_at": "La fecha debe incluir una zona horaria."})
    if not isinstance(notes, str) or len(notes) > 10000:
        raise ValidationError({"notes": "Las notas admiten hasta 10000 caracteres."})
    request_digest = ""
    if idempotency_key is not None:
        if not isinstance(idempotency_key, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{8,128}", idempotency_key
        ):
            raise ValidationError(
                {
                    "idempotency_key": "La clave admite entre 8 y 128 letras, números, guiones o guiones bajos."
                }
            )
        canonical = {
            "invoice": str(invoice.pk),
            "amount": str(payment_amount),
            "method": method,
            "reference": external_reference,
            "notes": notes,
            "received_at": received_at.astimezone(UTC).isoformat() if received_at else None,
        }
        request_digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
        previous = Payment.objects.filter(
            tenant=locked_tenant, idempotency_key=idempotency_key
        ).first()
        if previous:
            if previous.request_digest != request_digest:
                raise IdempotencyConflict()
            previous._idempotent_replay = True
            return previous

    # Una referencia externa no se puede reutilizar dentro
    # de la misma empresa y método de pago.
    if (
        external_reference
        and Payment.objects.filter(
            tenant=locked_tenant,
            method=method,
            external_reference=external_reference,
        ).exists()
    ):
        raise ValidationError({"external_reference": ("Esta referencia ya fue registrada.")})

    paid_balance = get_invoice_balance(invoice)

    if paid_balance <= 0:
        raise ValidationError({"amount": "La factura ya está totalmente pagada."})

    if payment_amount > paid_balance:
        raise ValidationError(
            {"amount": (f"El pago supera el saldo pendiente de {paid_balance} {invoice.currency}.")}
        )

    payment = Payment.objects.create(
        tenant=locked_tenant,
        invoice=invoice,
        recorded_by=actor,
        method=method,
        amount=payment_amount,
        external_reference=external_reference,
        received_at=received_at or timezone.now(),
        notes=notes,
        idempotency_key=idempotency_key,
        request_digest=request_digest,
    )

    record_audit_event(
        action=AuditEvent.Action.PAYMENT,
        entity_type="billing.payment",
        entity_id=str(payment.pk),
        tenant=locked_tenant,
        actor=actor,
        changes={
            "fields": {
                "amount": {
                    "before": None,
                    "after": str(payment.amount),
                },
                "method": {
                    "before": None,
                    "after": payment.method,
                },
            }
        },
        metadata={
            "operation": "payment_recorded",
            "invoice_id": str(invoice.pk),
            "currency": invoice.currency,
        },
        request=request,
    )

    return payment


@transaction.atomic
def reverse_payment(
    *,
    tenant,
    payment_id,
    actor,
    reason,
    request=None,
) -> PaymentReversal:
    """
    Revierte un pago sin modificar ni eliminar el registro original.

    Solo permite una reversión por pago. La reversión, su motivo
    y el evento de auditoría se registran en una transacción.
    """

    locked_tenant = (
        Tenant.objects.select_for_update()
        .filter(
            pk=tenant.pk,
            is_active=True,
        )
        .first()
    )

    if locked_tenant is None:
        raise ValidationError({"tenant": "La empresa no existe o no está activa."})

    _require_payment_role(
        tenant=locked_tenant,
        actor=actor,
        allowed_roles=REVERSAL_ROLES,
    )

    reason = reason.strip() if isinstance(reason, str) else ""

    if not reason:
        raise ValidationError({"reason": "El motivo de la reversión es obligatorio."})

    if len(reason) > 2000:
        raise ValidationError({"reason": "El motivo no puede superar los 2000 caracteres."})

    # Primera lectura para conocer la factura. Luego volvemos
    # a comprobar el pago tras adquirir los bloqueos.
    payment_reference = (
        Payment.objects.filter(
            pk=payment_id,
            tenant=locked_tenant,
        )
        .values("invoice_id")
        .first()
    )

    if payment_reference is None:
        raise ValidationError({"payment": "El pago no existe en esta empresa."})

    invoice = (
        Invoice.objects.select_for_update()
        .filter(
            pk=payment_reference["invoice_id"],
            tenant=locked_tenant,
        )
        .first()
    )

    if invoice is None:
        raise ValidationError({"invoice": "La factura no existe en esta empresa."})

    payment = (
        Payment.objects.select_for_update()
        .filter(
            pk=payment_id,
            tenant=locked_tenant,
            invoice=invoice,
        )
        .first()
    )

    if payment is None:
        raise ValidationError({"payment": "El pago no existe en esta empresa."})

    if PaymentReversal.objects.filter(payment=payment).exists():
        raise ValidationError({"payment": "Este pago ya fue revertido."})

    reversal = PaymentReversal.objects.create(
        tenant=locked_tenant,
        payment=payment,
        reversed_by=actor,
        reason=reason,
        occurred_at=timezone.now(),
    )

    record_audit_event(
        action=AuditEvent.Action.PAYMENT,
        entity_type="billing.payment_reversal",
        entity_id=str(reversal.pk),
        tenant=locked_tenant,
        actor=actor,
        changes={
            "fields": {
                "payment_id": {
                    "before": None,
                    "after": str(payment.pk),
                },
                "amount": {
                    "before": None,
                    "after": str(payment.amount),
                },
            }
        },
        metadata={
            "operation": "payment_reversed",
            "invoice_id": str(invoice.pk),
        },
        request=request,
    )

    return reversal
