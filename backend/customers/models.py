import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from tenancy.models import Tenant


class Customer(models.Model):
    """Cliente perteneciente a una empresa de la plataforma."""

    class CustomerType(models.TextChoices):
        INDIVIDUAL = "individual", "Persona física"
        COMPANY = "company", "Empresa"

    class DocumentType(models.TextChoices):
        CUIT = "cuit", "CUIT"
        CUIL = "cuil", "CUIL"
        DNI = "dni", "DNI"
        OTHER = "other", "Otro"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="customers",
    )

    customer_type = models.CharField(
        max_length=20,
        choices=CustomerType.choices,
        default=CustomerType.INDIVIDUAL,
    )

    name = models.CharField(
        max_length=150,
    )

    legal_name = models.CharField(
        max_length=200,
        blank=True,
    )

    document_type = models.CharField(
        max_length=10,
        choices=DocumentType.choices,
        blank=True,
        default="",
    )

    document_number = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    email = models.EmailField(
        blank=True,
    )

    phone = models.CharField(
        max_length=32,
        blank=True,
    )

    address = models.CharField(
        max_length=255,
        blank=True,
    )

    city = models.CharField(
        max_length=120,
        blank=True,
    )

    province = models.CharField(
        max_length=120,
        blank=True,
    )

    postal_code = models.CharField(
        max_length=20,
        blank=True,
    )

    country_code = models.CharField(
        max_length=2,
        default="AR",
    )

    notes = models.TextField(
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_customers",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "tenant",
                    "document_type",
                    "document_number",
                ],
                condition=Q(document_number__isnull=False),
                name="uniq_cust_doc_tenant",
            ),
        ]

        indexes = [
            models.Index(
                fields=["tenant", "is_active"],
                name="cust_tenant_active_idx",
            ),
            models.Index(
                fields=["tenant", "name"],
                name="cust_tenant_name_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip()

        if self.legal_name:
            self.legal_name = self.legal_name.strip()

        if self.document_number:
            document = self.document_number.strip()

            if self.document_type in {
                self.DocumentType.CUIT,
                self.DocumentType.CUIL,
                self.DocumentType.DNI,
            }:
                document = "".join(character for character in document if character.isdigit())
            else:
                document = document.upper()

            self.document_number = document or None
        else:
            self.document_number = None

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
