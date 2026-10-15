import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from catalog.models import Product
from customers.models import Customer
from tenancy.models import Tenant


class Invoice(models.Model):
    """Documento comercial perteneciente a una empresa."""

    class DocumentKind(models.TextChoices):
        INVOICE = "invoice", "Factura interna"
        CREDIT_NOTE = "credit_note", "Nota de crédito"
        DEBIT_NOTE = "debit_note", "Nota de débito"

    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        ISSUED = "issued", "Emitido"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="invoices",
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="invoices",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_invoices",
    )

    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issued_invoices",
    )

    document_kind = models.CharField(
        max_length=20,
        choices=DocumentKind.choices,
        default=DocumentKind.INVOICE,
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    # Numeración interna. No equivale al número fiscal de ARCA.
    internal_number = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    currency = models.CharField(
        max_length=3,
        default="ARS",
    )

    # Snapshot de los datos del cliente al crear el documento.
    customer_name_snapshot = models.CharField(
        max_length=150,
    )

    customer_legal_name_snapshot = models.CharField(
        max_length=200,
        blank=True,
    )

    customer_document_type_snapshot = models.CharField(
        max_length=10,
        blank=True,
    )

    customer_document_number_snapshot = models.CharField(
        max_length=30,
        blank=True,
    )

    customer_address_snapshot = models.CharField(
        max_length=255,
        blank=True,
    )

    customer_city_snapshot = models.CharField(
        max_length=120,
        blank=True,
    )

    customer_province_snapshot = models.CharField(
        max_length=120,
        blank=True,
    )

    customer_email_snapshot = models.EmailField(
        blank=True,
    )
    customer_country_code_snapshot = models.CharField(max_length=2, blank=True)
    customer_postal_code_snapshot = models.CharField(max_length=20, blank=True)

    subtotal = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    tax_total = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    total = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    notes = models.TextField(
        blank=True,
    )

    due_date = models.DateField(null=True, blank=True)
    payment_terms_days = models.PositiveSmallIntegerField(null=True, blank=True)
    issuer_snapshot = models.JSONField(default=dict, blank=True)
    footer_snapshot = models.CharField(max_length=1000, blank=True)

    issued_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "documento de facturación"
        verbose_name_plural = "documentos de facturación"
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "internal_number"],
                condition=Q(internal_number__isnull=False),
                name="uniq_bill_inv_number_tenant",
            ),
            models.CheckConstraint(
                condition=(
                    Q(subtotal__gte=Decimal("0.00"))
                    & Q(tax_total__gte=Decimal("0.00"))
                    & Q(total__gte=Decimal("0.00"))
                ),
                name="bill_inv_amounts_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(total=F("subtotal") + F("tax_total")),
                name="bill_inv_total_matches_parts",
            ),
        ]

        indexes = [
            models.Index(
                fields=["tenant", "status"],
                name="bill_inv_tenant_status_idx",
            ),
            models.Index(
                fields=["tenant", "created_at"],
                name="bill_inv_tenant_created_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if self.tenant_id and self.customer_id and self.customer.tenant_id != self.tenant_id:
            raise ValidationError(
                {"customer": ("El cliente debe pertenecer a la misma empresa que el documento.")}
            )

    def save(self, *args, **kwargs):
        """
        Impide crear documentos directamente como emitidos
        y modificar documentos una vez emitidos.

        La emisión se implementa mediante un servicio
        transaccional específico.
        """
        if self._state.adding:
            if self.status != self.Status.DRAFT:
                raise ValidationError("Los documentos deben crearse como borradores.")
        else:
            previous_status = (
                type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            )

            if previous_status == self.Status.ISSUED:
                raise ValidationError("Un documento emitido no puede modificarse.")

        if self.status == self.Status.ISSUED:
            if self.internal_number is None or self.issued_at is None or self.issued_by_id is None:
                raise ValidationError(
                    "La emisión requiere numeración interna, fecha y usuario emisor."
                )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Impide eliminar documentos emitidos."""
        if self.status == self.Status.ISSUED:
            raise ValidationError("Una factura emitida no puede eliminarse.")

        return super().delete(*args, **kwargs)

    def __str__(self):
        if self.internal_number is not None:
            return f"Documento interno #{self.internal_number}"

        return f"Borrador {self.pk}"


class InvoiceLine(models.Model):
    """Línea histórica de un documento de facturación."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="lines",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_lines",
    )

    position = models.PositiveSmallIntegerField()

    # Snapshot: cambios futuros en el catálogo no alteran el documento.
    description_snapshot = models.CharField(
        max_length=255,
    )

    sku_snapshot = models.CharField(
        max_length=64,
        blank=True,
    )

    unit_snapshot = models.CharField(
        max_length=20,
        blank=True,
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
    )

    unit_price = models.DecimalField(
        max_digits=16,
        decimal_places=4,
    )

    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    subtotal = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    tax_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    total = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "línea de facturación"
        verbose_name_plural = "líneas de facturación"
        ordering = ["position"]

        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "position"],
                name="uniq_bill_line_position",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=Decimal("0.000")),
                name="bill_line_quantity_positive",
            ),
            models.CheckConstraint(
                condition=(Q(unit_price__gte=Decimal("0.0000"))),
                name="bill_line_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=(Q(tax_rate__gte=Decimal("0.00")) & Q(tax_rate__lte=Decimal("100.00"))),
                name="bill_line_tax_valid",
            ),
            models.CheckConstraint(
                condition=Q(total=F("subtotal") + F("tax_amount")),
                name="bill_line_total_matches",
            ),
        ]

    def clean(self):
        super().clean()

        if self.invoice_id and self.product_id:
            if self.product.tenant_id != self.invoice.tenant_id:
                raise ValidationError(
                    {
                        "product": (
                            "El producto debe pertenecer a la misma empresa que el documento."
                        )
                    }
                )

            if self.product.currency != self.invoice.currency:
                raise ValidationError(
                    {"product": ("La moneda del producto debe coincidir con la del documento.")}
                )

        if self.invoice_id and self.invoice.status == Invoice.Status.ISSUED:
            raise ValidationError("No se pueden añadir o cambiar líneas de un documento emitido.")

    def save(self, *args, **kwargs):
        if self.invoice_id:
            if self.invoice.status == Invoice.Status.ISSUED:
                raise ValidationError("No se pueden añadir líneas a un documento emitido.")

        if not self._state.adding:
            previous_invoice_id = (
                type(self).objects.filter(pk=self.pk).values_list("invoice_id", flat=True).first()
            )

            if previous_invoice_id is not None:
                previous_status = (
                    Invoice.objects.filter(pk=previous_invoice_id)
                    .values_list("status", flat=True)
                    .first()
                )

                if previous_status == Invoice.Status.ISSUED:
                    raise ValidationError("No se pueden modificar líneas de un documento emitido.")

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.invoice.status == Invoice.Status.ISSUED:
            raise ValidationError("No se pueden eliminar líneas de un documento emitido.")

        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"Línea {self.position} - {self.description_snapshot}"


class Payment(models.Model):
    """Pago registrado para una factura emitida."""

    class Method(models.TextChoices):
        CASH = "cash", "Efectivo"
        BANK_TRANSFER = "bank_transfer", "Transferencia bancaria"
        DEBIT_CARD = "debit_card", "Tarjeta de débito"
        CREDIT_CARD = "credit_card", "Tarjeta de crédito"
        DIGITAL_WALLET = "digital_wallet", "Billetera virtual"
        CHECK = "check", "Cheque"
        OTHER = "other", "Otro"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="payments",
    )

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments",
    )

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )

    method = models.CharField(
        max_length=20,
        choices=Method.choices,
    )

    amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
    )

    external_reference = models.CharField(
        max_length=120,
        null=True,
        blank=True,
    )

    received_at = models.DateTimeField()
    idempotency_key = models.CharField(max_length=128, null=True, blank=True, editable=False)
    request_digest = models.CharField(max_length=64, blank=True, editable=False)

    notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "pago"
        verbose_name_plural = "pagos"
        ordering = ["-received_at", "-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="uniq_payment_idempotency_key",
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=Decimal("0.00")),
                name="payment_amount_positive",
            ),
            models.UniqueConstraint(
                fields=[
                    "tenant",
                    "method",
                    "external_reference",
                ],
                condition=Q(external_reference__isnull=False),
                name="uniq_payment_external_ref",
            ),
        ]

        indexes = [
            models.Index(
                fields=["tenant", "invoice"],
                name="payment_tenant_invoice_idx",
            ),
            models.Index(
                fields=["tenant", "received_at"],
                name="payment_tenant_received_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if self.tenant_id and self.invoice_id:
            if self.invoice.tenant_id != self.tenant_id:
                raise ValidationError(
                    {"invoice": ("La factura debe pertenecer a la misma empresa que el pago.")}
                )

        if self.invoice_id and self.invoice.status != Invoice.Status.ISSUED:
            raise ValidationError(
                {"invoice": ("Solo se pueden registrar pagos sobre facturas emitidas.")}
            )

        if self.amount is not None and self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": "El importe del pago debe ser positivo."})

    def save(self, *args, **kwargs):
        """Los pagos registrados no se modifican."""
        if not self._state.adding:
            raise ValidationError(
                "Un pago registrado no puede modificarse. Utilizá el proceso de reversión."
            )

        if self.external_reference:
            self.external_reference = self.external_reference.strip() or None

        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Un pago registrado no puede eliminarse.")

    def __str__(self):
        return f"Pago de {self.amount} para la factura {self.invoice_id}"


class PaymentReversal(models.Model):
    """Reversión explícita de un pago registrado."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="payment_reversals",
    )

    payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,
        related_name="reversal",
    )

    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_reversals",
    )

    reason = models.TextField()

    occurred_at = models.DateTimeField()

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "reversión de pago"
        verbose_name_plural = "reversiones de pagos"
        ordering = ["-occurred_at"]

        indexes = [
            models.Index(
                fields=["tenant", "occurred_at"],
                name="payrev_tenant_time_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if self.tenant_id and self.payment_id:
            if self.payment.tenant_id != self.tenant_id:
                raise ValidationError(
                    {"payment": ("El pago debe pertenecer a la misma empresa que la reversión.")}
                )

        if not self.reason or not self.reason.strip():
            raise ValidationError({"reason": "El motivo de la reversión es obligatorio."})

    def save(self, *args, **kwargs):
        """Las reversiones son registros de solo creación."""
        if not self._state.adding:
            raise ValidationError("Una reversión registrada no puede modificarse.")

        self.reason = self.reason.strip()
        self.full_clean()

        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Una reversión registrada no puede eliminarse.")

    def __str__(self):
        return f"Reversión del pago {self.payment_id}"
