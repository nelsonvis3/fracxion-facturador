from django.test import TestCase
from rest_framework.test import APIClient

from auditlog.models import AuditEvent

from .models import Payment
from .services import get_invoice_balance, record_payment, reverse_payment
from .test_regressions import BillingFixtures


class PaymentIdempotencyTests(BillingFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.invoice = self.issued()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/api/tenants/{self.tenant.pk}/payments/"
        self.payload = {"invoice": str(self.invoice.pk), "method": "cash", "amount": "100.00"}

    def test_full_payment_retry_has_one_effect_and_one_event(self):
        first = self.client.post(
            self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="request-full-payment"
        )
        second = self.client.post(
            self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="request-full-payment"
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(second["Idempotent-Replayed"], "true")
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(entity_type="billing.payment").count(), 1)
        self.assertEqual(get_invoice_balance(self.invoice), 0)

    def test_reused_key_with_different_data_is_conflict(self):
        self.client.post(
            self.url,
            {**self.payload, "amount": "10.00"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="request-conflict",
        )
        response = self.client.post(
            self.url,
            {**self.payload, "amount": "20.00"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="request-conflict",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Payment.objects.count(), 1)

    def test_revoked_membership_cannot_replay_and_reversal_is_not_repaid(self):
        payment = record_payment(
            tenant=self.tenant,
            invoice_id=self.invoice.pk,
            actor=self.user,
            amount="100.00",
            method="cash",
            idempotency_key="original-full-payment",
        )
        reverse_payment(
            tenant=self.tenant, payment_id=payment.pk, actor=self.user, reason="Correction"
        )
        replay = record_payment(
            tenant=self.tenant,
            invoice_id=self.invoice.pk,
            actor=self.user,
            amount="100.00",
            method="cash",
            idempotency_key="original-full-payment",
        )
        self.assertEqual(payment.pk, replay.pk)
        self.assertEqual(get_invoice_balance(self.invoice), 100)
        self.membership.is_active = False
        self.membership.save()
        self.assertEqual(
            self.client.post(
                self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="original-full-payment"
            ).status_code,
            403,
        )

    def test_reference_replay_does_not_trigger_duplicate_reference_error(self):
        data = {**self.payload, "external_reference": "bank-reference"}
        for _ in range(2):
            response = self.client.post(
                self.url, data, format="json", HTTP_IDEMPOTENCY_KEY="request-reference"
            )
            self.assertEqual(response.status_code, 201)
        self.assertEqual(Payment.objects.count(), 1)

    def test_legacy_requests_without_key_remain_separate_payments(self):
        for _ in range(2):
            self.assertEqual(
                self.client.post(
                    self.url, {**self.payload, "amount": "10.00"}, format="json"
                ).status_code,
                201,
            )
        self.assertEqual(Payment.objects.count(), 2)

    def test_invalid_key_cannot_write(self):
        for key in ["short", "x" * 129, "invalid key with spaces"]:
            self.assertEqual(
                self.client.post(
                    self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY=key
                ).status_code,
                400,
            )
        self.assertFalse(Payment.objects.exists())
