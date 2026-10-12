from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from catalog.models import Product
from customers.models import Customer
from tenancy.models import Membership, Tenant

from .models import Invoice, InvoiceLine, Payment
from .services import create_invoice_draft, issue_invoice, record_payment, reverse_payment


class BillingFixtures:
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Regression", slug="regression")
        self.user = get_user_model().objects.create_user(email="billing-regression@example.com")
        self.membership = Membership.objects.create(
            tenant=self.tenant, user=self.user, role="owner"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, name="Customer", country_code="AR", postal_code="3600"
        )
        self.product = Product.objects.create(
            tenant=self.tenant,
            name="Service",
            unit_price=Decimal("100"),
            tax_rate=Decimal("0"),
            currency="ARS",
        )

    def draft(self, **kwargs):
        data = {
            "tenant": self.tenant,
            "customer_id": self.customer.pk,
            "actor": self.user,
            "currency": "ARS",
            "lines": [{"product": self.product.pk, "quantity": Decimal("1")}],
        }
        data.update(kwargs)
        return create_invoice_draft(**data)

    def issued(self):
        return issue_invoice(tenant=self.tenant, invoice_id=self.draft().pk, actor=self.user)


class BillingRegressionTests(BillingFixtures, TestCase):
    def test_direct_draft_service_checks_roles(self):
        for role in ["viewer", "sales", "accountant"]:
            self.membership.role = role
            self.membership.save()
            with self.assertRaises(PermissionDenied):
                self.draft()
        self.assertFalse(Invoice.objects.exists())

    def test_draft_rejects_revoked_membership(self):
        self.membership.is_active = False
        self.membership.save()
        with self.assertRaises(PermissionDenied):
            self.draft()

    def test_draft_rechecks_inactive_tenant(self):
        Tenant.objects.filter(pk=self.tenant.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            self.draft()

    def test_catalog_maximum_price_fits_invoice_line(self):
        self.product.unit_price = Decimal("999999999999.99")
        self.product.save()
        invoice = self.draft()
        self.assertEqual(invoice.lines.get().unit_price, Decimal("999999999999.9900"))

    def test_overflow_is_400_and_rolls_back(self):
        self.product.unit_price = Decimal("999999999999.99")
        self.product.save()
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.post(
            f"/api/tenants/{self.tenant.pk}/invoices/",
            {
                "customer": str(self.customer.pk),
                "currency": "ARS",
                "lines": [{"product": str(self.product.pk), "quantity": "999999999.999"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Invoice.objects.exists())
        self.assertFalse(InvoiceLine.objects.exists())

    def test_accumulated_overflow_rolls_back_all_lines(self):
        self.product.unit_price = Decimal("999999999999.99")
        self.product.save()
        with self.assertRaises(ValidationError):
            self.draft(lines=[{"product": self.product.pk, "quantity": Decimal("60")}] * 2)
        self.assertFalse(Invoice.objects.exists())

    def test_direct_service_rejects_invalid_quantities(self):
        for quantity in ["NaN", "Infinity", "0.0001", "1000000000", "-1"]:
            with self.assertRaises(ValidationError):
                self.draft(lines=[{"product": self.product.pk, "quantity": quantity}])

    def test_invalid_payment_method_returns_validation_error(self):
        invoice = self.issued()
        with self.assertRaises(ValidationError):
            record_payment(
                tenant=self.tenant,
                invoice_id=invoice.pk,
                actor=self.user,
                method="invalid",
                amount="1",
            )

    def test_api_balance_excludes_reversed_payments(self):
        invoice = self.issued()
        payment = record_payment(
            tenant=self.tenant, invoice_id=invoice.pk, actor=self.user, method="cash", amount="40"
        )
        client = APIClient()
        client.force_authenticate(self.user)
        url = f"/api/tenants/{self.tenant.pk}/invoices/{invoice.pk}/"
        self.assertEqual(client.get(url).data["balance"], "60.00")
        reverse_payment(
            tenant=self.tenant, payment_id=payment.pk, actor=self.user, reason="Correction"
        )
        self.assertEqual(client.get(url).data["balance"], "100.00")
        self.assertEqual(client.get(url).data["paid_total"], "0.00")

    def test_snapshot_includes_country_and_postal_code(self):
        invoice = self.draft()
        self.assertEqual(invoice.customer_country_code_snapshot, "AR")
        self.assertEqual(invoice.customer_postal_code_snapshot, "3600")


class BillingConcurrencyTests(BillingFixtures, TransactionTestCase):
    def concurrent(self, operations):
        barrier = Barrier(len(operations))

        def run(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation()
            except ValidationError:
                return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            return list(executor.map(run, operations))

    def test_concurrent_issue_allocates_distinct_numbers(self):
        ids = [self.draft().pk, self.draft().pk]
        results = self.concurrent(
            [
                lambda invoice_id=pk: (
                    issue_invoice(
                        tenant=self.tenant, invoice_id=invoice_id, actor=self.user
                    ).internal_number
                )
                for pk in ids
            ]
        )
        self.assertEqual(set(results), {1, 2})

    def test_concurrent_payments_cannot_overpay(self):
        invoice = self.issued()

        def pay():
            return record_payment(
                tenant=self.tenant,
                invoice_id=invoice.pk,
                actor=self.user,
                method="cash",
                amount="80",
            ).pk

        results = self.concurrent([pay, pay])
        self.assertEqual(results.count("rejected"), 1)
        self.assertEqual(Payment.objects.count(), 1)

    def test_concurrent_reference_cannot_duplicate(self):
        invoice = self.issued()

        def pay():
            return record_payment(
                tenant=self.tenant,
                invoice_id=invoice.pk,
                actor=self.user,
                method="cash",
                amount="30",
                external_reference="same-reference",
            ).pk

        results = self.concurrent([pay, pay])
        self.assertEqual(results.count("rejected"), 1)
        self.assertEqual(Payment.objects.count(), 1)
