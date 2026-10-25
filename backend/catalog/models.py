import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q

from tenancy.models import Tenant


class Product(models.Model):
    """Producto o servicio perteneciente a una empresa."""

    class ProductType(models.TextChoices):
        PRODUCT = "product", "Producto"
        SERVICE = "service", "Servicio"

    class Unit(models.TextChoices):
        UNIT = "unit", "Unidad"
        HOUR = "hour", "Hora"
        KILOGRAM = "kg", "Kilogramo"
        LITER = "liter", "Litro"
        METER = "meter", "Metro"
        PACK = "pack", "Paquete"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="products",
    )

    sku = models.CharField(
        max_length=64,
        null=True,
        blank=True,
    )

    name = models.CharField(
        max_length=180,
    )

    description = models.TextField(
        blank=True,
    )

    product_type = models.CharField(
        max_length=20,
        choices=ProductType.choices,
        default=ProductType.PRODUCT,
    )

    unit = models.CharField(
        max_length=20,
        choices=Unit.choices,
        default=Unit.UNIT,
    )

    unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    currency = models.CharField(
        max_length=3,
        default="ARS",
    )

    # Porcentaje explícito, por ejemplo Decimal("21.00").
    # No se presupone una tasa fiscal automática.
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "producto"
        verbose_name_plural = "productos"
        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "sku"],
                condition=Q(sku__isnull=False),
                name="uniq_product_sku_tenant",
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=Decimal("0.00")),
                name="product_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=(Q(tax_rate__gte=Decimal("0.00")) & Q(tax_rate__lte=Decimal("100.00"))),
                name="product_tax_rate_valid",
            ),
        ]

        indexes = [
            models.Index(
                fields=["tenant", "is_active"],
                name="product_tenant_active_idx",
            ),
            models.Index(
                fields=["tenant", "name"],
                name="product_tenant_name_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip()

        if self.sku:
            self.sku = self.sku.strip().upper() or None
        else:
            self.sku = None

        if self.currency:
            self.currency = self.currency.strip().upper()

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
