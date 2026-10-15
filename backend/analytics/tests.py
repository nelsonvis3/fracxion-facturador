from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Event
from unittest.mock import patch

from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from billing.services import issue_invoice, record_payment, reverse_payment
from billing.test_regressions import BillingFixtures
from catalog.models import Product
from tenancy.models import BusinessSettings

from .services import overview


class AnalyticsTests(BillingFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/api/tenants/{self.tenant.pk}/analytics/overview/"
        self.filters = {"date_from": "2026-10-01", "date_to": "2026-10-31", "currency": "ARS"}

    def issue(self, *, at=datetime(2026, 10, 14, 15, tzinfo=UTC), **kwargs):
        with patch("billing.services.timezone.now", return_value=at):
            draft = self.draft(**kwargs)
            return issue_invoice(tenant=self.tenant, invoice_id=draft.pk, actor=self.user)

    def test_lines_and_multiple_payments_do_not_multiply_totals(self):
        invoice = self.issue(lines=[{"product": self.product.pk, "quantity": "1"}] * 2)
        for n in ["50.00", "25.00"]:
            record_payment(
                tenant=self.tenant,
                invoice_id=invoice.pk,
                actor=self.user,
                method="cash",
                amount=n,
                received_at=datetime(2026, 10, 14, 16, tzinfo=UTC),
            )
        result = overview(self.tenant, self.filters)
        self.assertEqual(result["metrics"]["invoiced"], "200.00")
        self.assertEqual(result["metrics"]["collected"], "75.00")
        self.assertEqual(result["metrics"]["outstanding"], "125.00")
        self.assertEqual(
            result["monthly"], [{"month": "2026-10", "invoiced": "200.00", "collected": "75.00"}]
        )
        self.assertEqual(result["products"][0]["invoiced"], "200.00")

    def test_currency_and_customer_filters_are_effective(self):
        self.issue()
        usd = Product.objects.create(
            tenant=self.tenant,
            name="USD product",
            currency="USD",
            unit_price="900.00",
            tax_rate="0",
        )
        self.issue(currency="USD", lines=[{"product": usd.pk, "quantity": "1"}])
        self.assertEqual(overview(self.tenant, self.filters)["metrics"]["invoiced"], "100.00")
        self.assertEqual(
            overview(self.tenant, self.filters | {"currency": "USD"})["metrics"]["invoiced"],
            "900.00",
        )
        self.assertEqual(
            overview(
                self.tenant, self.filters | {"customer": "00000000-0000-4000-8000-000000000099"}
            )["metrics"]["invoiced"],
            "0.00",
        )

    def test_reversals_and_aging_use_effective_current_balance(self):
        invoice = self.issue(due_date=date(2026, 9, 10))
        payment = record_payment(
            tenant=self.tenant,
            invoice_id=invoice.pk,
            actor=self.user,
            method="cash",
            amount="40",
            received_at=datetime(2026, 10, 14, 16, tzinfo=UTC),
        )
        reverse_payment(
            tenant=self.tenant, payment_id=payment.pk, actor=self.user, reason="Correction"
        )
        with patch("analytics.services.timezone.localdate", return_value=date(2026, 10, 14)):
            result = overview(self.tenant, self.filters)
        self.assertEqual(result["metrics"]["collected"], "0.00")
        self.assertEqual(result["metrics"]["overdue"], "100.00")
        self.assertEqual(
            next(r for r in result["aging"] if r["bucket"] == "31_60")["balance"], "100.00"
        )

    def test_business_timezone_bounds_include_correct_events(self):
        BusinessSettings.objects.create(tenant=self.tenant, timezone="America/New_York")
        for at in [
            datetime(2026, 10, 1, 2, tzinfo=UTC),
            datetime(2026, 10, 1, 5, tzinfo=UTC),
            datetime(2026, 11, 1, 3, tzinfo=UTC),
        ]:
            self.issue(at=at)
        result = overview(self.tenant, self.filters)
        self.assertEqual(result["metrics"]["invoiced"], "200.00")
        self.assertEqual(result["previous"]["metrics"]["invoiced"], "100.00")

    def test_zero_period_and_bad_ranges_are_safe(self):
        result = overview(self.tenant, self.filters)
        self.assertEqual(result["metrics"]["invoiced"], "0.00")
        self.assertEqual(result["metrics"]["issued_count"], 0)
        for data in [
            {"currency": "ZZZ"},
            {"date_from": "2026-11-01", "date_to": "2026-01-01"},
            {"date_from": "0001-01-01", "date_to": "0001-01-01"},
            {"date_from": "9999-12-31", "date_to": "9999-12-31"},
        ]:
            self.assertEqual(self.client.get(self.url, data).status_code, 400)

    def test_query_count_is_independent_of_invoice_count(self):
        self.issue()
        with CaptureQueriesContext(connection) as first:
            overview(self.tenant, self.filters)
        for _ in range(10):
            self.issue()
        with CaptureQueriesContext(connection) as second:
            overview(self.tenant, self.filters)
        self.assertEqual(len(first), len(second))
        self.assertLessEqual(len(second), 20)

    def test_roles_and_tenant_access(self):
        for role in ["owner", "admin", "accountant", "sales", "viewer"]:
            self.membership.role = role
            self.membership.save()
            self.assertEqual(
                self.client.get(self.url, self.filters).status_code,
                200 if role in {"owner", "admin", "accountant"} else 403,
            )
            self.assertEqual(
                self.client.get(f"/api/tenants/{self.tenant.pk}/analytics/records/").status_code,
                200,
            )
        self.membership.is_active = False
        self.membership.save()
        self.assertEqual(self.client.get(self.url, self.filters).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url, self.filters).status_code, 401)


class ConcurrentReportTests(BillingFixtures, TransactionTestCase):
    def test_report_preserves_one_snapshot_while_payment_commits(self):
        from .services import period_metrics

        invoice = self.issued()
        metrics_read, payment_done = Event(), Event()

        def writer():
            try:
                if not metrics_read.wait(timeout=10):
                    raise RuntimeError("Report did not start")
                record_payment(
                    tenant=self.tenant,
                    invoice_id=invoice.pk,
                    actor=self.user,
                    method="cash",
                    amount="30.00",
                )
                payment_done.set()
            finally:
                connections.close_all()

        calls = 0

        def read_then_allow_writer(*args, **kwargs):
            nonlocal calls
            result = period_metrics(*args, **kwargs)
            calls += 1
            if calls == 1:
                metrics_read.set()
                if not payment_done.wait(timeout=10):
                    raise RuntimeError("Concurrent payment did not commit")
            return result

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(writer)
            with patch("analytics.services.period_metrics", side_effect=read_then_allow_writer):
                result = overview(self.tenant, {"currency": "ARS"})
            future.result(timeout=10)
        self.assertEqual(result["metrics"]["collected"], "0.00")
        self.assertTrue(all(row["collected"] == "0.00" for row in result["monthly"]))
        self.assertEqual(
            overview(self.tenant, {"currency": "ARS"})["metrics"]["collected"], "30.00"
        )
