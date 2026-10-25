import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Supplier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    name = models.CharField(max_length=180)
    legal_name = models.CharField(max_length=200, blank=True)
    tax_id = models.CharField(max_length=40, blank=True)
    country_code = models.CharField(max_length=2, default="AR")
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    notes = models.CharField(max_length=2000, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "tax_id"],
                condition=~Q(tax_id=""),
                name="supplier_tenant_tax_unique",
            )
        ]
        indexes = [models.Index(fields=["tenant", "is_active", "name"], name="supplier_search_idx")]


class InventoryPolicy(models.Model):
    product = models.OneToOneField(
        "catalog.Product",
        primary_key=True,
        on_delete=models.PROTECT,
        related_name="inventory_policy",
    )
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    tracking = models.BooleanField(default=True)
    minimum = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(minimum__gte=0), name="inventory_minimum_valid")
        ]


class InventoryMovement(models.Model):
    class Kind(models.TextChoices):
        IN = "in", "Entrada"
        OUT = "out", "Salida"
        ADJUSTMENT = "adjustment", "Ajuste"
        REVERSAL = "reversal", "Reversión"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="inventory_movements"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    delta = models.DecimalField(max_digits=12, decimal_places=3)
    balance_after = models.DecimalField(max_digits=12, decimal_places=3)
    reason = models.CharField(max_length=500)
    reference = models.CharField(max_length=120, blank=True)
    product_name_snapshot = models.CharField(max_length=180)
    unit_snapshot = models.CharField(max_length=20)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reverses = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_by"
    )
    idempotency_key = models.CharField(max_length=128)
    request_digest = models.CharField(max_length=64)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"], name="inventory_tenant_request_unique"
            ),
            models.CheckConstraint(condition=~Q(delta=0), name="inventory_delta_nonzero"),
            models.CheckConstraint(
                condition=Q(balance_after__gte=0), name="inventory_balance_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(kind="in", delta__gt=0)
                | Q(kind="out", delta__lt=0)
                | Q(kind__in=["adjustment", "reversal"]),
                name="inventory_direction_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "product", "-occurred_at"], name="inventory_product_ledger_idx"
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Los movimientos son inmutables. Registrá una corrección explícita."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("El historial de inventario no se elimina.")


class ExpenseCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="expense_category_unique")
        ]


class Expense(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        POSTED = "posted", "Registrado"
        VOID = "void", "Anulado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, null=True, blank=True)
    purchase_order = models.ForeignKey(
        "PurchaseOrder", on_delete=models.PROTECT, null=True, blank=True, related_name="expenses"
    )
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, null=True, blank=True)
    supplier_name_snapshot = models.CharField(max_length=180, blank=True)
    category_name_snapshot = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=1000)
    reference = models.CharField(max_length=120, blank=True)
    incurred_on = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3)
    net_amount = models.DecimalField(max_digits=14, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2)
    total = models.DecimalField(max_digits=16, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    attachment = models.BinaryField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="posted_expenses",
    )
    void_reason = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_expenses"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-incurred_on", "-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(net_amount__gt=0), name="expense_net_positive"),
            models.CheckConstraint(
                condition=Q(tax_rate__gte=0, tax_rate__lte=100), name="expense_tax_valid"
            ),
            models.CheckConstraint(
                condition=Q(total=models.F("net_amount") + models.F("tax_amount")),
                name="expense_total_consistent",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "currency", "status", "incurred_on"], name="expense_reporting_idx"
            ),
            models.Index(fields=["tenant", "due_date"], name="expense_due_idx"),
        ]

    def save(self, *args, **kwargs):
        if (
            not self._state.adding
            and type(self).objects.filter(pk=self.pk).exclude(status="draft").exists()
        ):
            raise ValidationError("Un gasto registrado es inmutable. Usá su anulación autorizada.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los gastos se conservan; anulá el registro cuando corresponda.")


class ExpensePayment(models.Model):
    class Method(models.TextChoices):
        CASH = "cash", "Efectivo"
        TRANSFER = "transfer", "Transferencia"
        CARD = "card", "Tarjeta"
        OTHER = "other", "Otro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    expense = models.ForeignKey(Expense, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    method = models.CharField(
        max_length=20,
        choices=Method.choices,
    )
    reference = models.CharField(max_length=120, blank=True)
    paid_at = models.DateTimeField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=128)
    request_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="expense_payment_positive"),
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"], name="expense_payment_request_unique"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "expense", "paid_at"], name="expense_payment_lookup_idx")
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Un pago registrado no se modifica.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Un pago se revierte; su historia no se elimina.")


class ExpensePaymentReversal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    payment = models.OneToOneField(
        ExpensePayment, on_delete=models.PROTECT, related_name="reversal"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    occurred_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Una reversión es inmutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Una reversión no se elimina.")


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        ORDERED = "ordered", "Pedido confirmado"
        CLOSED = "closed", "Cerrado"
        CANCELLED = "cancelled", "Cancelado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    supplier_name_snapshot = models.CharField(max_length=180, blank=True)
    reference = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=2000, blank=True)
    currency = models.CharField(max_length=3)
    expected_on = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    net_amount = models.DecimalField(max_digits=16, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2)
    total = models.DecimalField(max_digits=16, decimal_places=2)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["tenant", "status", "created_at"], name="purchase_status_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(net_amount__gte=0, tax_amount__gte=0), name="purchase_amounts_valid"
            ),
            models.CheckConstraint(
                condition=Q(total=models.F("net_amount") + models.F("tax_amount")),
                name="purchase_total_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        if (
            not self._state.adding
            and type(self).objects.filter(pk=self.pk).exclude(status="draft").exists()
        ):
            raise ValidationError(
                "Un pedido confirmado es inmutable; registrá sus recepciones o cierre."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los pedidos se conservan en el historial.")


class PurchaseLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    position = models.PositiveSmallIntegerField()
    product_name_snapshot = models.CharField(max_length=180)
    product_type_snapshot = models.CharField(max_length=20)
    unit_snapshot = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2)
    net_amount = models.DecimalField(max_digits=16, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2)
    total = models.DecimalField(max_digits=16, decimal_places=2)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "position"], name="purchase_line_position_unique"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0, unit_cost__gte=0, tax_rate__gte=0, tax_rate__lte=100),
                name="purchase_line_values_valid",
            ),
            models.CheckConstraint(
                condition=Q(total=models.F("net_amount") + models.F("tax_amount")),
                name="purchase_line_total_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.order.status != "draft" or not self._state.adding:
            raise ValidationError("Las líneas confirmadas se conservan sin editar.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Las líneas confirmadas se conservan sin eliminar.")


class ReceiptRecord(models.Model):
    """Append-only records; concrete subclasses define protected references."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("El historial de recepción es inmutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("El historial de recepción no se elimina.")


class PurchaseReceipt(ReceiptRecord):
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="receipts")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reference = models.CharField(max_length=120, blank=True)
    idempotency_key = models.CharField(max_length=128)
    request_digest = models.CharField(max_length=64)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"], name="purchase_receipt_request_unique"
            )
        ]


class PurchaseReceiptLine(ReceiptRecord):
    receipt = models.ForeignKey(PurchaseReceipt, on_delete=models.PROTECT, related_name="lines")
    line = models.ForeignKey(PurchaseLine, on_delete=models.PROTECT, related_name="receipt_lines")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    movement = models.OneToOneField(
        InventoryMovement,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_receipt_line",
    )

    class Meta:
        ordering = ["line__position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["receipt", "line"], name="receipt_order_line_unique"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="receipt_quantity_positive"),
        ]


class PurchaseReceiptReversal(ReceiptRecord):
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    receipt = models.OneToOneField(
        PurchaseReceipt, on_delete=models.PROTECT, related_name="reversal"
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(max_length=500)
    occurred_at = models.DateTimeField(auto_now_add=True)
