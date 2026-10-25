from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APITestCase

from auditlog.models import AuditEvent
from catalog.models import Product
from customers.models import Customer
from tenancy.models import Membership, Tenant

from .models import (
    Invoice,
    InvoiceLine,
    Payment,
    PaymentReversal,
)
from .services import (
    create_invoice_draft,
    get_invoice_balance,
    issue_invoice,
    record_payment,
    reverse_payment,
)

User = get_user_model()


class InvoiceDraftServiceTests(TestCase):
    """Pruebas del servicio transaccional de facturación."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Empresa Alpha",
            slug="empresa-alpha",
        )

        self.user = User.objects.create_user(
            email="facturacion.alpha@example.com",
            password="TestPassword123!",
        )
        Membership.objects.create(tenant=self.tenant, user=self.user, role=Membership.Role.OWNER)

        self.customer = Customer.objects.create(
            tenant=self.tenant,
            customer_type=Customer.CustomerType.COMPANY,
            name="Cliente de Prueba",
            legal_name="Cliente de Prueba S.A.",
            document_type=Customer.DocumentType.CUIT,
            document_number="20301234567",
            email="cliente@example.com",
            address="Calle 123",
            city="Formosa",
            province="Formosa",
        )

        self.product = Product.objects.create(
            tenant=self.tenant,
            sku="TEST-001",
            name="Servicio de Prueba",
            description="Descripción del servicio",
            product_type=Product.ProductType.SERVICE,
            unit=Product.Unit.UNIT,
            unit_price=Decimal("100.00"),
            currency="ARS",
            tax_rate=Decimal("21.00"),
        )

    def create_draft(self, **overrides):
        params = {
            "tenant": self.tenant,
            "customer_id": self.customer.pk,
            "currency": "ARS",
            "lines": [
                {
                    "product": self.product.pk,
                    "quantity": Decimal("2.000"),
                },
            ],
            "actor": self.user,
        }
        params.update(overrides)

        return create_invoice_draft(**params)

    def test_creates_draft_with_correct_amounts(self):
        invoice = self.create_draft()

        self.assertEqual(
            invoice.status,
            Invoice.Status.DRAFT,
        )
        self.assertIsNone(invoice.internal_number)

        self.assertEqual(invoice.subtotal, Decimal("200.00"))
        self.assertEqual(invoice.tax_total, Decimal("42.00"))
        self.assertEqual(invoice.total, Decimal("242.00"))

        self.assertEqual(invoice.lines.count(), 1)

        line = invoice.lines.get()

        self.assertEqual(line.quantity, Decimal("2.000"))
        self.assertEqual(line.unit_price, Decimal("100.0000"))
        self.assertEqual(line.subtotal, Decimal("200.00"))
        self.assertEqual(line.tax_amount, Decimal("42.00"))
        self.assertEqual(line.total, Decimal("242.00"))

    def test_records_invoice_creation_in_audit(self):
        invoice = self.create_draft()

        event = AuditEvent.objects.get(
            tenant=self.tenant,
            actor=self.user,
            action=AuditEvent.Action.CREATE,
            entity_type="billing.invoice",
            entity_id=str(invoice.pk),
        )

        self.assertEqual(
            event.changes["fields"]["total"]["after"],
            "242.00",
        )
        self.assertEqual(event.metadata["line_count"], 1)

    def test_preserves_customer_and_product_snapshots(self):
        invoice = self.create_draft()
        line = invoice.lines.get()

        self.customer.name = "Nombre Modificado"
        self.customer.save()

        self.product.name = "Servicio Actualizado"
        self.product.unit_price = Decimal("500.00")
        self.product.save()

        invoice.refresh_from_db()
        line.refresh_from_db()

        self.assertEqual(
            invoice.customer_name_snapshot,
            "Cliente de Prueba",
        )
        self.assertEqual(
            line.description_snapshot,
            "Servicio de Prueba",
        )
        self.assertEqual(
            line.unit_price,
            Decimal("100.0000"),
        )
        self.assertEqual(invoice.total, Decimal("242.00"))

    def test_rejects_customer_from_another_tenant(self):
        other_tenant = Tenant.objects.create(
            name="Empresa Beta",
            slug="empresa-beta",
        )

        foreign_customer = Customer.objects.create(
            tenant=other_tenant,
            name="Cliente Externo",
        )

        with self.assertRaises(ValidationError):
            self.create_draft(
                customer_id=foreign_customer.pk,
            )

        self.assertEqual(Invoice.objects.count(), 0)

    def test_rejects_product_from_another_tenant(self):
        other_tenant = Tenant.objects.create(
            name="Empresa Beta",
            slug="empresa-beta",
        )

        foreign_product = Product.objects.create(
            tenant=other_tenant,
            sku="FOREIGN-001",
            name="Producto Externo",
            unit_price=Decimal("100.00"),
            currency="ARS",
            tax_rate=Decimal("21.00"),
        )

        with self.assertRaises(ValidationError):
            self.create_draft(
                lines=[
                    {
                        "product": foreign_product.pk,
                        "quantity": Decimal("1.000"),
                    },
                ],
            )

        self.assertEqual(Invoice.objects.count(), 0)

    def test_rejects_mismatched_currency(self):
        with self.assertRaises(ValidationError):
            self.create_draft(currency="USD")

        self.assertEqual(Invoice.objects.count(), 0)

    def test_rejects_empty_lines(self):
        with self.assertRaises(ValidationError):
            self.create_draft(lines=[])

        self.assertEqual(Invoice.objects.count(), 0)

    def test_rejects_zero_quantity(self):
        with self.assertRaises(ValidationError):
            self.create_draft(
                lines=[
                    {
                        "product": self.product.pk,
                        "quantity": Decimal("0.000"),
                    },
                ],
            )

        self.assertEqual(Invoice.objects.count(), 0)

    def test_audit_failure_rolls_back_invoice_and_lines(self):
        with patch(
            "billing.services.record_audit_event",
            side_effect=RuntimeError("Auditoría no disponible"),
        ):
            with self.assertRaises(RuntimeError):
                self.create_draft()

        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(InvoiceLine.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)


class InvoiceIssueServiceTests(TestCase):
    """Pruebas de emisión, numeración, permisos y auditoría."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Empresa Emisora",
            slug="empresa-emisora",
        )

        self.owner = User.objects.create_user(
            email="owner.emision@example.com",
            password="TestPassword123!",
        )

        self.viewer = User.objects.create_user(
            email="viewer.emision@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            tenant=self.tenant,
            user=self.owner,
            role=Membership.Role.OWNER,
        )

        Membership.objects.create(
            tenant=self.tenant,
            user=self.viewer,
            role=Membership.Role.VIEWER,
        )

        self.customer = Customer.objects.create(
            tenant=self.tenant,
            name="Cliente Emisión",
            document_type=Customer.DocumentType.CUIT,
            document_number="20301234567",
        )

        self.product = Product.objects.create(
            tenant=self.tenant,
            sku="EMISION-001",
            name="Servicio Emisión",
            product_type=Product.ProductType.SERVICE,
            unit=Product.Unit.UNIT,
            unit_price=Decimal("100.00"),
            currency="ARS",
            tax_rate=Decimal("21.00"),
        )

    def create_draft(self, **overrides):
        params = {
            "tenant": self.tenant,
            "customer_id": self.customer.pk,
            "currency": "ARS",
            "lines": [
                {
                    "product": self.product.pk,
                    "quantity": Decimal("2.000"),
                },
            ],
            "actor": self.owner,
        }
        params.update(overrides)

        return create_invoice_draft(**params)

    def issue(self, invoice, actor=None, tenant=None):
        return issue_invoice(
            tenant=tenant or self.tenant,
            invoice_id=invoice.pk,
            actor=actor or self.owner,
        )

    def create_other_tenant_invoice(self):
        other_tenant = Tenant.objects.create(
            name="Empresa Segunda",
            slug="empresa-segunda",
        )

        other_owner = User.objects.create_user(
            email="owner.segunda@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            tenant=other_tenant,
            user=other_owner,
            role=Membership.Role.OWNER,
        )

        other_customer = Customer.objects.create(
            tenant=other_tenant,
            name="Cliente Segunda",
        )

        other_product = Product.objects.create(
            tenant=other_tenant,
            sku="SEGUNDA-001",
            name="Producto Segunda",
            unit_price=Decimal("50.00"),
            currency="ARS",
            tax_rate=Decimal("21.00"),
        )

        invoice = create_invoice_draft(
            tenant=other_tenant,
            customer_id=other_customer.pk,
            currency="ARS",
            lines=[
                {
                    "product": other_product.pk,
                    "quantity": Decimal("1.000"),
                },
            ],
            actor=other_owner,
        )

        return other_tenant, other_owner, invoice

    def test_issue_assigns_number_and_records_audit(self):
        invoice = self.create_draft()

        issued = self.issue(invoice)

        self.assertEqual(
            issued.status,
            Invoice.Status.ISSUED,
        )
        self.assertEqual(issued.internal_number, 1)
        self.assertEqual(issued.issued_by, self.owner)
        self.assertIsNotNone(issued.issued_at)

        event = AuditEvent.objects.get(
            tenant=self.tenant,
            actor=self.owner,
            action=AuditEvent.Action.ISSUE,
            entity_type="billing.invoice",
            entity_id=str(invoice.pk),
        )

        self.assertEqual(
            event.changes["fields"]["internal_number"]["after"],
            1,
        )
        self.assertEqual(
            event.metadata["numbering_type"],
            "internal",
        )

    def test_numbers_increment_for_same_tenant(self):
        first = self.create_draft()
        second = self.create_draft()

        issued_first = self.issue(first)
        issued_second = self.issue(second)

        self.assertEqual(issued_first.internal_number, 1)
        self.assertEqual(issued_second.internal_number, 2)

    def test_numbering_starts_at_one_for_another_tenant(self):
        first = self.create_draft()
        issued_first = self.issue(first)

        other_tenant, other_owner, other_invoice = self.create_other_tenant_invoice()

        issued_other = self.issue(
            other_invoice,
            actor=other_owner,
            tenant=other_tenant,
        )

        self.assertEqual(issued_first.internal_number, 1)
        self.assertEqual(issued_other.internal_number, 1)

    def test_cannot_issue_same_invoice_twice(self):
        invoice = self.create_draft()

        self.issue(invoice)

        with self.assertRaises(ValidationError):
            self.issue(invoice)

        self.assertEqual(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                action=AuditEvent.Action.ISSUE,
                entity_id=str(invoice.pk),
            ).count(),
            1,
        )

    def test_viewer_cannot_issue_invoice(self):
        invoice = self.create_draft()

        with self.assertRaises(PermissionDenied):
            self.issue(invoice, actor=self.viewer)

        invoice.refresh_from_db()

        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        self.assertIsNone(invoice.internal_number)

    def test_user_without_membership_cannot_issue(self):
        outsider = User.objects.create_user(
            email="outsider.emision@example.com",
            password="TestPassword123!",
        )

        invoice = self.create_draft()

        with self.assertRaises(PermissionDenied):
            self.issue(invoice, actor=outsider)

        invoice.refresh_from_db()

        self.assertEqual(invoice.status, Invoice.Status.DRAFT)

    def test_cannot_issue_invoice_from_another_tenant(self):
        _, _, foreign_invoice = self.create_other_tenant_invoice()

        with self.assertRaises(ValidationError):
            self.issue(foreign_invoice)

        foreign_invoice.refresh_from_db()

        self.assertEqual(
            foreign_invoice.status,
            Invoice.Status.DRAFT,
        )
        self.assertIsNone(foreign_invoice.internal_number)

    def test_audit_failure_rolls_back_issue(self):
        invoice = self.create_draft()

        with patch(
            "billing.services.record_audit_event",
            side_effect=RuntimeError("Auditoría no disponible"),
        ):
            with self.assertRaises(RuntimeError):
                self.issue(invoice)

        invoice.refresh_from_db()

        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        self.assertIsNone(invoice.internal_number)
        self.assertIsNone(invoice.issued_at)
        self.assertIsNone(invoice.issued_by)

        self.assertFalse(
            AuditEvent.objects.filter(
                tenant=self.tenant,
                action=AuditEvent.Action.ISSUE,
                entity_id=str(invoice.pk),
            ).exists()
        )

    def test_inconsistent_line_amounts_cannot_be_issued(self):
        invoice = self.create_draft()
        line = invoice.lines.get()

        # Simula una modificación que elude los métodos normales
        # del modelo, manteniendo la restricción subtotal + impuesto.
        InvoiceLine.objects.filter(pk=line.pk).update(
            subtotal=Decimal("999.00"),
            total=Decimal("1041.00"),
        )

        with self.assertRaises(ValidationError):
            self.issue(invoice)

        invoice.refresh_from_db()

        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        self.assertIsNone(invoice.internal_number)

    def test_invoice_without_lines_cannot_be_issued(self):
        invoice = Invoice.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            created_by=self.owner,
            currency="ARS",
            customer_name_snapshot=self.customer.name,
        )

        with self.assertRaises(ValidationError):
            self.issue(invoice)

        invoice.refresh_from_db()

        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        self.assertIsNone(invoice.internal_number)

    def test_issued_invoice_cannot_be_deleted_by_instance(self):
        invoice = self.create_draft()
        self.issue(invoice)

        invoice.refresh_from_db()

        with self.assertRaises(DjangoValidationError):
            invoice.delete()

        self.assertTrue(Invoice.objects.filter(pk=invoice.pk).exists())


class InvoiceAPITests(APITestCase):
    """Pruebas HTTP de seguridad y facturación multi-tenant."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            name="Empresa HTTP Alpha",
            slug="http-alpha",
        )

        self.tenant_b = Tenant.objects.create(
            name="Empresa HTTP Beta",
            slug="http-beta",
        )

        self.owner_a = User.objects.create_user(
            email="http.alpha@example.com",
            password="TestPassword123!",
        )

        self.owner_b = User.objects.create_user(
            email="http.beta@example.com",
            password="TestPassword123!",
        )

        self.viewer_a = User.objects.create_user(
            email="http.viewer@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            tenant=self.tenant_a,
            user=self.owner_a,
            role=Membership.Role.OWNER,
        )

        Membership.objects.create(
            tenant=self.tenant_b,
            user=self.owner_b,
            role=Membership.Role.OWNER,
        )

        Membership.objects.create(
            tenant=self.tenant_a,
            user=self.viewer_a,
            role=Membership.Role.VIEWER,
        )

        self.customer_a = Customer.objects.create(
            tenant=self.tenant_a,
            name="Cliente HTTP Alpha",
            document_type=Customer.DocumentType.CUIT,
            document_number="20111222333",
        )

        self.customer_b = Customer.objects.create(
            tenant=self.tenant_b,
            name="Cliente HTTP Beta",
            document_type=Customer.DocumentType.CUIT,
            document_number="20444555666",
        )

        self.product_a = Product.objects.create(
            tenant=self.tenant_a,
            sku="HTTP-ALPHA-001",
            name="Servicio HTTP Alpha",
            unit_price=Decimal("100.00"),
            currency="ARS",
            tax_rate=Decimal("21.00"),
        )

        self.product_b = Product.objects.create(
            tenant=self.tenant_b,
            sku="HTTP-BETA-001",
            name="Servicio HTTP Beta",
            unit_price=Decimal("500.00"),
            currency="ARS",
            tax_rate=Decimal("10.50"),
        )

        # Facturas de prueba para verificar el aislamiento.
        self.invoice_a = create_invoice_draft(
            tenant=self.tenant_a,
            customer_id=self.customer_a.pk,
            currency="ARS",
            lines=[
                {
                    "product": self.product_a.pk,
                    "quantity": Decimal("1.000"),
                },
            ],
            actor=self.owner_a,
        )

        self.invoice_b = create_invoice_draft(
            tenant=self.tenant_b,
            customer_id=self.customer_b.pk,
            currency="ARS",
            lines=[
                {
                    "product": self.product_b.pk,
                    "quantity": Decimal("1.000"),
                },
            ],
            actor=self.owner_b,
        )

        self.client.force_authenticate(user=self.owner_a)

    def invoice_list_url(self, tenant):
        return f"/api/tenants/{tenant.pk}/invoices/"

    def invoice_detail_url(self, tenant, invoice):
        return f"/api/tenants/{tenant.pk}/invoices/{invoice.pk}/"

    def invoice_issue_url(self, tenant, invoice):
        return self.invoice_detail_url(tenant, invoice) + "issue/"

    def create_payload(self, **overrides):
        payload = {
            "customer": str(self.customer_a.pk),
            "currency": "ARS",
            "lines": [
                {
                    "product": str(self.product_a.pk),
                    "quantity": "2.000",
                },
            ],
            "notes": "Borrador de prueba",
        }
        payload.update(overrides)
        return payload

    def test_list_only_returns_own_tenant_invoices(self):
        response = self.client.get(self.invoice_list_url(self.tenant_a))

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {str(item["id"]) for item in response.data["results"]}

        self.assertIn(str(self.invoice_a.pk), returned_ids)
        self.assertNotIn(str(self.invoice_b.pk), returned_ids)

    def test_cannot_list_another_tenant_invoices(self):
        response = self.client.get(self.invoice_list_url(self.tenant_b))

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_cannot_retrieve_foreign_invoice_by_uuid(self):
        response = self.client.get(
            self.invoice_detail_url(
                self.tenant_a,
                self.invoice_b,
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_create_draft_calculates_amounts_on_server(self):
        payload = self.create_payload()

        # Estos campos no forman parte del serializer de entrada.
        # Intentamos manipular el precio y el total desde el cliente.
        payload["lines"][0]["unit_price"] = "0.01"
        payload["lines"][0]["tax_rate"] = "0.00"
        payload["total"] = "0.01"

        response = self.client.post(
            self.invoice_list_url(self.tenant_a),
            payload,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        self.assertEqual(
            response.data["subtotal"],
            "200.00",
        )
        self.assertEqual(
            response.data["tax_total"],
            "42.00",
        )
        self.assertEqual(
            response.data["total"],
            "242.00",
        )

        invoice = Invoice.objects.get(pk=response.data["id"])

        self.assertEqual(invoice.tenant, self.tenant_a)
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)

    def test_cannot_create_invoice_with_foreign_customer(self):
        response = self.client.post(
            self.invoice_list_url(self.tenant_a),
            self.create_payload(
                customer=str(self.customer_b.pk),
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_cannot_create_invoice_with_foreign_product(self):
        response = self.client.post(
            self.invoice_list_url(self.tenant_a),
            self.create_payload(
                lines=[
                    {
                        "product": str(self.product_b.pk),
                        "quantity": "1.000",
                    },
                ],
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_viewer_cannot_create_invoice(self):
        self.client.force_authenticate(user=self.viewer_a)

        response = self.client.post(
            self.invoice_list_url(self.tenant_a),
            self.create_payload(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_owner_can_issue_invoice_through_api(self):
        response = self.client.post(
            self.invoice_issue_url(
                self.tenant_a,
                self.invoice_a,
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )

        self.assertEqual(
            response.data["status"],
            Invoice.Status.ISSUED,
        )
        self.assertEqual(
            response.data["internal_number"],
            1,
        )

    def test_cannot_issue_same_invoice_twice(self):
        url = self.invoice_issue_url(
            self.tenant_a,
            self.invoice_a,
        )

        first_response = self.client.post(url)
        second_response = self.client.post(url)

        self.assertEqual(
            first_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            second_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_viewer_cannot_issue_invoice(self):
        self.client.force_authenticate(user=self.viewer_a)

        response = self.client.post(
            self.invoice_issue_url(
                self.tenant_a,
                self.invoice_a,
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.invoice_a.refresh_from_db()

        self.assertEqual(
            self.invoice_a.status,
            Invoice.Status.DRAFT,
        )

    def test_generic_update_is_not_available(self):
        response = self.client.patch(
            self.invoice_detail_url(
                self.tenant_a,
                self.invoice_a,
            ),
            {"notes": "Intento de alterar la factura"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class PaymentServiceTests(TestCase):
    """Pruebas de pagos, saldos, reversiones y auditoría."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Empresa Pagos",
            slug="empresa-pagos",
        )

        self.owner = User.objects.create_user(
            email="owner.pagos@example.com",
            password="TestPassword123!",
        )

        self.accountant = User.objects.create_user(
            email="contador.pagos@example.com",
            password="TestPassword123!",
        )

        self.viewer = User.objects.create_user(
            email="visor.pagos@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            tenant=self.tenant,
            user=self.owner,
            role=Membership.Role.OWNER,
        )

        Membership.objects.create(
            tenant=self.tenant,
            user=self.accountant,
            role=Membership.Role.ACCOUNTANT,
        )

        Membership.objects.create(
            tenant=self.tenant,
            user=self.viewer,
            role=Membership.Role.VIEWER,
        )

        self.customer = Customer.objects.create(
            tenant=self.tenant,
            name="Cliente Pagos",
            document_type=Customer.DocumentType.CUIT,
            document_number="20123456786",
        )

        self.product = Product.objects.create(
            tenant=self.tenant,
            sku="PAGOS-001",
            name="Servicio de prueba",
            unit_price=Decimal("100.00"),
            currency="ARS",
            tax_rate=Decimal("21.00"),
        )

        draft = create_invoice_draft(
            tenant=self.tenant,
            customer_id=self.customer.pk,
            currency="ARS",
            lines=[
                {
                    "product": self.product.pk,
                    "quantity": Decimal("1.000"),
                },
            ],
            actor=self.owner,
        )

        self.invoice = issue_invoice(
            tenant=self.tenant,
            invoice_id=draft.pk,
            actor=self.owner,
        )

        # Total esperado: ARS 121,00.
        self.assertEqual(
            self.invoice.total,
            Decimal("121.00"),
        )

    def pay(self, amount="40.00", **overrides):
        params = {
            "tenant": self.tenant,
            "invoice_id": self.invoice.pk,
            "actor": self.owner,
            "method": Payment.Method.BANK_TRANSFER,
            "amount": amount,
        }
        params.update(overrides)

        return record_payment(**params)

    def test_partial_payment_reduces_balance(self):
        payment = self.pay("40.00")

        self.assertEqual(
            payment.amount,
            Decimal("40.00"),
        )

        self.assertEqual(
            get_invoice_balance(self.invoice),
            Decimal("81.00"),
        )

    def test_full_payment_clears_balance(self):
        self.pay("121.00")

        self.assertEqual(
            get_invoice_balance(self.invoice),
            Decimal("0.00"),
        )

    def test_overpayment_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.pay("121.01")

        self.assertEqual(Payment.objects.count(), 0)

        self.assertEqual(
            get_invoice_balance(self.invoice),
            Decimal("121.00"),
        )

    def test_cannot_pay_invoice_from_another_tenant(self):
        other_tenant = Tenant.objects.create(
            name="Empresa Ajena",
            slug="empresa-ajena",
        )

        other_customer = Customer.objects.create(
            tenant=other_tenant,
            name="Cliente Ajeno",
        )

        other_product = Product.objects.create(
            tenant=other_tenant,
            name="Producto Ajeno",
            unit_price=Decimal("100.00"),
            currency="ARS",
            tax_rate=Decimal("21.00"),
        )

        other_owner = User.objects.create_user(
            email="owner.ajeno@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            tenant=other_tenant,
            user=other_owner,
            role=Membership.Role.OWNER,
        )

        draft = create_invoice_draft(
            tenant=other_tenant,
            customer_id=other_customer.pk,
            currency="ARS",
            lines=[
                {
                    "product": other_product.pk,
                    "quantity": Decimal("1.000"),
                },
            ],
            actor=other_owner,
        )

        foreign_invoice = issue_invoice(
            tenant=other_tenant,
            invoice_id=draft.pk,
            actor=other_owner,
        )

        with self.assertRaises(ValidationError):
            self.pay(
                "10.00",
                invoice_id=foreign_invoice.pk,
            )

        self.assertEqual(Payment.objects.count(), 0)

    def test_draft_invoice_cannot_receive_payment(self):
        draft = create_invoice_draft(
            tenant=self.tenant,
            customer_id=self.customer.pk,
            currency="ARS",
            lines=[
                {
                    "product": self.product.pk,
                    "quantity": Decimal("1.000"),
                },
            ],
            actor=self.owner,
        )

        with self.assertRaises(ValidationError):
            self.pay(
                "10.00",
                invoice_id=draft.pk,
            )

        self.assertEqual(Payment.objects.count(), 0)

    def test_accountant_can_record_payment(self):
        payment = self.pay(
            "20.00",
            actor=self.accountant,
        )

        self.assertEqual(
            payment.recorded_by,
            self.accountant,
        )

    def test_viewer_cannot_record_payment(self):
        with self.assertRaises(PermissionDenied):
            self.pay(
                "20.00",
                actor=self.viewer,
            )

        self.assertEqual(Payment.objects.count(), 0)

    def test_duplicate_external_reference_is_rejected(self):
        self.pay(
            "10.00",
            external_reference="TRANSFER-001",
        )

        with self.assertRaises(ValidationError):
            self.pay(
                "10.00",
                external_reference="TRANSFER-001",
            )

        self.assertEqual(Payment.objects.count(), 1)

    def test_reverse_payment_restores_balance(self):
        payment = self.pay("40.00")

        self.assertEqual(
            get_invoice_balance(self.invoice),
            Decimal("81.00"),
        )

        reversal = reverse_payment(
            tenant=self.tenant,
            payment_id=payment.pk,
            actor=self.owner,
            reason="Transferencia recibida y luego anulada.",
        )

        self.assertEqual(reversal.payment_id, payment.pk)

        self.assertEqual(
            get_invoice_balance(self.invoice),
            Decimal("121.00"),
        )

        # El pago original se conserva como evidencia histórica.
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

        self.assertTrue(
            PaymentReversal.objects.filter(
                payment=payment,
            ).exists()
        )

    def test_payment_cannot_be_reversed_twice(self):
        payment = self.pay("40.00")

        reverse_payment(
            tenant=self.tenant,
            payment_id=payment.pk,
            actor=self.owner,
            reason="Primera reversión.",
        )

        with self.assertRaises(ValidationError):
            reverse_payment(
                tenant=self.tenant,
                payment_id=payment.pk,
                actor=self.owner,
                reason="Segunda reversión.",
            )

        self.assertEqual(
            PaymentReversal.objects.filter(
                payment=payment,
            ).count(),
            1,
        )

    def test_viewer_cannot_reverse_payment(self):
        payment = self.pay("40.00")

        with self.assertRaises(PermissionDenied):
            reverse_payment(
                tenant=self.tenant,
                payment_id=payment.pk,
                actor=self.viewer,
                reason="Intento no autorizado.",
            )

        self.assertFalse(
            PaymentReversal.objects.filter(
                payment=payment,
            ).exists()
        )

    def test_reversal_requires_a_reason(self):
        payment = self.pay("40.00")

        with self.assertRaises(ValidationError):
            reverse_payment(
                tenant=self.tenant,
                payment_id=payment.pk,
                actor=self.owner,
                reason="   ",
            )

        self.assertFalse(
            PaymentReversal.objects.filter(
                payment=payment,
            ).exists()
        )

    def test_audit_failure_rolls_back_payment(self):
        with patch(
            "billing.services.record_audit_event",
            side_effect=RuntimeError("Auditoría no disponible"),
        ):
            with self.assertRaises(RuntimeError):
                self.pay("40.00")

        self.assertEqual(Payment.objects.count(), 0)

        self.assertEqual(
            get_invoice_balance(self.invoice),
            Decimal("121.00"),
        )

    def test_audit_failure_rolls_back_reversal(self):
        payment = self.pay("40.00")

        with patch(
            "billing.services.record_audit_event",
            side_effect=RuntimeError("Auditoría no disponible"),
        ):
            with self.assertRaises(RuntimeError):
                reverse_payment(
                    tenant=self.tenant,
                    payment_id=payment.pk,
                    actor=self.owner,
                    reason="Reversión de prueba.",
                )

        self.assertFalse(
            PaymentReversal.objects.filter(
                payment=payment,
            ).exists()
        )

        self.assertEqual(
            get_invoice_balance(self.invoice),
            Decimal("81.00"),
        )


class PaymentAPITests(APITestCase):
    """Pruebas HTTP de pagos y reversiones multi-tenant."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            name="Empresa Pagos HTTP A",
            slug="pagos-http-a",
        )

        self.tenant_b = Tenant.objects.create(
            name="Empresa Pagos HTTP B",
            slug="pagos-http-b",
        )

        self.owner_a = User.objects.create_user(
            email="owner.payment.a@example.com",
            password="TestPassword123!",
        )

        self.owner_b = User.objects.create_user(
            email="owner.payment.b@example.com",
            password="TestPassword123!",
        )

        self.accountant_a = User.objects.create_user(
            email="accountant.payment.a@example.com",
            password="TestPassword123!",
        )

        self.viewer_a = User.objects.create_user(
            email="viewer.payment.a@example.com",
            password="TestPassword123!",
        )

        Membership.objects.create(
            tenant=self.tenant_a,
            user=self.owner_a,
            role=Membership.Role.OWNER,
        )

        Membership.objects.create(
            tenant=self.tenant_b,
            user=self.owner_b,
            role=Membership.Role.OWNER,
        )

        Membership.objects.create(
            tenant=self.tenant_a,
            user=self.accountant_a,
            role=Membership.Role.ACCOUNTANT,
        )

        Membership.objects.create(
            tenant=self.tenant_a,
            user=self.viewer_a,
            role=Membership.Role.VIEWER,
        )

        self.customer_a = Customer.objects.create(
            tenant=self.tenant_a,
            name="Cliente Pago A",
        )

        self.customer_b = Customer.objects.create(
            tenant=self.tenant_b,
            name="Cliente Pago B",
        )

        self.product_a = Product.objects.create(
            tenant=self.tenant_a,
            sku="PAY-HTTP-A",
            name="Servicio A",
            unit_price=Decimal("100.00"),
            currency="ARS",
            tax_rate=Decimal("21.00"),
        )

        self.product_b = Product.objects.create(
            tenant=self.tenant_b,
            sku="PAY-HTTP-B",
            name="Servicio B",
            unit_price=Decimal("100.00"),
            currency="ARS",
            tax_rate=Decimal("21.00"),
        )

        draft_a = create_invoice_draft(
            tenant=self.tenant_a,
            customer_id=self.customer_a.pk,
            currency="ARS",
            lines=[
                {
                    "product": self.product_a.pk,
                    "quantity": Decimal("1.000"),
                },
            ],
            actor=self.owner_a,
        )

        draft_b = create_invoice_draft(
            tenant=self.tenant_b,
            customer_id=self.customer_b.pk,
            currency="ARS",
            lines=[
                {
                    "product": self.product_b.pk,
                    "quantity": Decimal("1.000"),
                },
            ],
            actor=self.owner_b,
        )

        self.invoice_a = issue_invoice(
            tenant=self.tenant_a,
            invoice_id=draft_a.pk,
            actor=self.owner_a,
        )

        self.invoice_b = issue_invoice(
            tenant=self.tenant_b,
            invoice_id=draft_b.pk,
            actor=self.owner_b,
        )

        # Pago de la empresa B para las pruebas de aislamiento.
        self.payment_b = record_payment(
            tenant=self.tenant_b,
            invoice_id=self.invoice_b.pk,
            actor=self.owner_b,
            method=Payment.Method.BANK_TRANSFER,
            amount=Decimal("10.00"),
        )

        self.client.force_authenticate(user=self.owner_a)

    def payment_list_url(self, tenant):
        return f"/api/tenants/{tenant.pk}/payments/"

    def payment_detail_url(self, tenant, payment):
        return f"/api/tenants/{tenant.pk}/payments/{payment.pk}/"

    def payment_reverse_url(self, tenant, payment):
        return (
            self.payment_detail_url(
                tenant,
                payment,
            )
            + "reverse/"
        )

    def create_payload(self, **overrides):
        payload = {
            "invoice": str(self.invoice_a.pk),
            "method": "bank_transfer",
            "amount": "20.00",
            "external_reference": "PAY-HTTP-001",
            "notes": "Pago de prueba",
        }
        payload.update(overrides)
        return payload

    def test_list_only_returns_own_tenant_payments(self):
        payment_a = record_payment(
            tenant=self.tenant_a,
            invoice_id=self.invoice_a.pk,
            actor=self.owner_a,
            method=Payment.Method.BANK_TRANSFER,
            amount=Decimal("20.00"),
        )

        response = self.client.get(self.payment_list_url(self.tenant_a))

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {str(item["id"]) for item in response.data["results"]}

        self.assertIn(str(payment_a.pk), returned_ids)
        self.assertNotIn(str(self.payment_b.pk), returned_ids)

    def test_cannot_list_another_tenant_payments(self):
        response = self.client.get(self.payment_list_url(self.tenant_b))

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_cannot_retrieve_foreign_payment(self):
        response = self.client.get(
            self.payment_detail_url(
                self.tenant_a,
                self.payment_b,
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_accountant_can_register_payment(self):
        self.client.force_authenticate(
            user=self.accountant_a,
        )

        response = self.client.post(
            self.payment_list_url(self.tenant_a),
            self.create_payload(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        payment = Payment.objects.get(pk=response.data["id"])

        self.assertEqual(payment.tenant, self.tenant_a)
        self.assertEqual(payment.recorded_by, self.accountant_a)
        self.assertEqual(payment.amount, Decimal("20.00"))

    def test_viewer_cannot_register_payment(self):
        self.client.force_authenticate(
            user=self.viewer_a,
        )

        response = self.client.post(
            self.payment_list_url(self.tenant_a),
            self.create_payload(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_overpayment_is_rejected_over_http(self):
        response = self.client.post(
            self.payment_list_url(self.tenant_a),
            self.create_payload(amount="121.01"),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertFalse(
            Payment.objects.filter(
                tenant=self.tenant_a,
                invoice=self.invoice_a,
            ).exists()
        )

    def test_duplicate_external_reference_is_rejected(self):
        first = self.client.post(
            self.payment_list_url(self.tenant_a),
            self.create_payload(),
            format="json",
        )

        self.assertEqual(
            first.status_code,
            status.HTTP_201_CREATED,
            first.data,
        )

        second = self.client.post(
            self.payment_list_url(self.tenant_a),
            self.create_payload(),
            format="json",
        )

        self.assertEqual(
            second.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            Payment.objects.filter(
                tenant=self.tenant_a,
                external_reference="PAY-HTTP-001",
            ).count(),
            1,
        )

    def test_owner_can_reverse_payment_over_http(self):
        payment = record_payment(
            tenant=self.tenant_a,
            invoice_id=self.invoice_a.pk,
            actor=self.owner_a,
            method=Payment.Method.BANK_TRANSFER,
            amount=Decimal("20.00"),
        )

        response = self.client.post(
            self.payment_reverse_url(
                self.tenant_a,
                payment,
            ),
            {
                "reason": "Transferencia anulada.",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        self.assertEqual(
            str(response.data["payment"]),
            str(payment.pk),
        )

        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

        self.assertEqual(
            get_invoice_balance(self.invoice_a),
            Decimal("121.00"),
        )

    def test_accountant_cannot_reverse_payment(self):
        payment = record_payment(
            tenant=self.tenant_a,
            invoice_id=self.invoice_a.pk,
            actor=self.owner_a,
            method=Payment.Method.BANK_TRANSFER,
            amount=Decimal("20.00"),
        )

        self.client.force_authenticate(
            user=self.accountant_a,
        )

        response = self.client.post(
            self.payment_reverse_url(
                self.tenant_a,
                payment,
            ),
            {
                "reason": "Intento de reversión.",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertFalse(
            PaymentReversal.objects.filter(
                payment=payment,
            ).exists()
        )

    def test_reversal_requires_reason(self):
        payment = record_payment(
            tenant=self.tenant_a,
            invoice_id=self.invoice_a.pk,
            actor=self.owner_a,
            method=Payment.Method.BANK_TRANSFER,
            amount=Decimal("20.00"),
        )

        response = self.client.post(
            self.payment_reverse_url(
                self.tenant_a,
                payment,
            ),
            {
                "reason": "   ",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertFalse(
            PaymentReversal.objects.filter(
                payment=payment,
            ).exists()
        )

    def test_delete_payment_is_not_supported(self):
        payment = record_payment(
            tenant=self.tenant_a,
            invoice_id=self.invoice_a.pk,
            actor=self.owner_a,
            method=Payment.Method.BANK_TRANSFER,
            amount=Decimal("20.00"),
        )

        response = self.client.delete(
            self.payment_detail_url(
                self.tenant_a,
                payment,
            )
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
