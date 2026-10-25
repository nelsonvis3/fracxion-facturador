from datetime import date, timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError as ModelValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from billing.services import issue_invoice, record_payment
from billing.test_regressions import BillingFixtures
from tenancy.models import BusinessSettings


class ReceivableTests(BillingFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.base = f"/api/tenants/{self.tenant.pk}/invoices/"

    def test_historical_or_unscheduled_documents_never_invent_due_dates(self):
        invoice = self.issued()
        response = self.client.get(f"{self.base}{invoice.pk}/")
        self.assertIsNone(response.data["due_date"])
        self.assertIsNone(response.data["days_overdue"])
        self.assertEqual(response.data["receivable_status"], "unscheduled")
        self.assertEqual(self.client.get(self.base, {"receivable": "overdue"}).data["count"], 0)

    def test_default_terms_snapshot_and_issuer_are_frozen(self):
        BusinessSettings.objects.create(
            tenant=self.tenant,
            payment_terms_days=30,
            timezone="UTC",
            invoice_footer="Original footer",
        )
        with patch("billing.services.timezone.localdate", return_value=date(2026, 10, 14)):
            invoice = self.draft()
        self.assertEqual(invoice.due_date, date(2026, 11, 13))
        self.assertEqual(invoice.payment_terms_days, 30)
        self.assertEqual(invoice.footer_snapshot, "Original footer")
        invoice = issue_invoice(tenant=self.tenant, invoice_id=invoice.pk, actor=self.user)
        invoice.due_date = date(2027, 1, 1)
        with self.assertRaises(ModelValidationError):
            invoice.save()
        BusinessSettings.objects.filter(tenant=self.tenant).update(
            payment_terms_days=60, invoice_footer="New"
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.footer_snapshot, "Original footer")

    def test_paid_overdue_and_due_today_filters_use_real_balance(self):
        today = date(2026, 10, 14)
        invoices = []
        for due in [today - timedelta(days=1), today, today + timedelta(days=3), None]:
            invoice = self.draft(due_date=due)
            invoices.append(
                issue_invoice(tenant=self.tenant, invoice_id=invoice.pk, actor=self.user)
            )
        with patch("billing.receivables.business_today", return_value=today):
            for state, invoice in zip(
                ["overdue", "due_today", "upcoming", "unscheduled"], invoices
            ):
                data = self.client.get(self.base, {"receivable": state}).data
                self.assertEqual(data["count"], 1)
                self.assertEqual(data["results"][0]["id"], str(invoice.pk))
            self.assertEqual(self.client.get(self.base, {"receivable": "unpaid"}).data["count"], 4)
            record_payment(
                tenant=self.tenant,
                invoice_id=invoices[0].pk,
                actor=self.user,
                amount="100",
                method="cash",
            )
            self.assertEqual(self.client.get(self.base, {"receivable": "overdue"}).data["count"], 0)
            self.assertEqual(self.client.get(self.base, {"receivable": "paid"}).data["count"], 1)

    def test_due_date_validation_and_issued_api_immutability(self):
        payload = {
            "customer": str(self.customer.pk),
            "currency": "ARS",
            "lines": [{"product": str(self.product.pk), "quantity": "1"}],
            "due_date": "not-a-date",
        }
        self.assertEqual(self.client.post(self.base, payload, format="json").status_code, 400)
        invoice = self.issued()
        self.assertEqual(
            self.client.patch(
                f"{self.base}{invoice.pk}/", {"due_date": "2027-01-01"}, format="json"
            ).status_code,
            405,
        )
        for params in [
            {"receivable": "invalid"},
            {"due_from": "2026-12-01", "due_to": "2026-01-01"},
            {"due_window": 0},
        ]:
            self.assertEqual(self.client.get(self.base, params).status_code, 400)
