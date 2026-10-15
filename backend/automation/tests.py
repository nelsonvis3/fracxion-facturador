from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from billing.services import issue_invoice, record_payment
from billing.test_regressions import BillingFixtures
from tenancy.models import BusinessSettings, Membership, Tenant

from .models import AutomationRule, Job, JobAttempt, Notification
from .services import claim_job, execute_job, request_report, save_rule, schedule_due


class JobTests(BillingFixtures, TestCase):
    def setUp(self):
        super().setUp()
        from django.core.cache import cache

        cache.clear()
        self.invoice = self.issued()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.base = f"/api/tenants/{self.tenant.pk}"

    def job(self, params=None):
        return request_report(
            tenant_id=self.tenant.pk, actor=self.user, params=params or {"file_format": "csv"}
        )

    def test_durable_report_and_private_download_rechecks_permissions(self):
        job = self.job()
        self.assertEqual(
            self.client.get(f"{self.base}/reports/jobs/{job.pk}/download/").status_code, 404
        )
        self.assertTrue(execute_job(claim_job()))
        response = self.client.get(f"{self.base}/reports/jobs/{job.pk}/download/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"100.00", response.content)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(Notification.objects.filter(job=job).count(), 1)
        self.membership.role = "viewer"
        self.membership.save()
        self.assertEqual(
            self.client.get(f"{self.base}/reports/jobs/{job.pk}/download/").status_code, 403
        )

    def test_failed_execution_retries_with_bounded_backoff_and_no_secret_errors(self):
        job = self.job()
        for attempt in range(1, 4):
            Job.objects.filter(pk=job.pk).update(available_at=timezone.now() - timedelta(seconds=1))
            claimed = claim_job()
            with patch(
                "automation.services.render_report",
                side_effect=RuntimeError("synthetic SECRET should never be stored"),
            ):
                self.assertFalse(execute_job(claimed))
            job.refresh_from_db()
            self.assertEqual(job.attempts, attempt)
            self.assertEqual(job.error_code, "execution_failed")
            self.assertEqual(job.status, "failed" if attempt == 3 else "pending")
        self.assertEqual(JobAttempt.objects.filter(job=job).count(), 3)
        retry = self.client.post(f"{self.base}/reports/jobs/{job.pk}/retry/", {}, format="json")
        self.assertEqual(retry.status_code, 202)
        self.assertNotEqual(str(job.pk), retry.data["id"])

    def test_lease_recovery_fences_old_worker_and_does_not_duplicate_notifications(self):
        job = self.job()
        old = claim_job()
        Job.objects.filter(pk=job.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
        recovered = claim_job()
        self.assertNotEqual(old.lease_id, recovered.lease_id)
        self.assertFalse(execute_job(old))
        self.assertTrue(execute_job(recovered))
        self.assertFalse(execute_job(recovered))
        self.assertEqual(Notification.objects.filter(job=job).count(), 1)
        self.assertEqual(JobAttempt.objects.get(job=job, number=1).outcome, "lease_expired")

    def test_membership_and_company_revocation_cancel_pending_effects(self):
        for field in ["membership", "company"]:
            job = self.job()
            claimed = claim_job()
            if field == "membership":
                Membership.objects.filter(pk=self.membership.pk).update(is_active=False)
            else:
                Tenant.objects.filter(pk=self.tenant.pk).update(is_active=False)
            self.assertFalse(execute_job(claimed))
            job.refresh_from_db()
            self.assertEqual(job.status, "cancelled")
            self.assertIsNone(job.result)
            Membership.objects.filter(pk=self.membership.pk).update(is_active=True)
            Tenant.objects.filter(pk=self.tenant.pk).update(is_active=True)

    def test_no_other_member_or_tenant_can_download_or_read_my_notifications(self):
        job = self.job()
        execute_job(claim_job())
        other = get_user_model().objects.create_user(email="other-job@example.com")
        Membership.objects.create(tenant=self.tenant, user=other, role="owner")
        self.client.force_authenticate(other)
        self.assertEqual(
            self.client.get(f"{self.base}/reports/jobs/{job.pk}/download/").status_code, 404
        )
        self.assertEqual(self.client.get(f"{self.base}/notifications/").data["count"], 0)
        notification = Notification.objects.get(job=job)
        self.assertEqual(
            self.client.post(f"{self.base}/notifications/{notification.pk}/read/", {}).status_code,
            404,
        )

    def test_notification_read_is_idempotent_and_expires_export(self):
        job = self.job()
        execute_job(claim_job())
        item = Notification.objects.get(job=job)
        url = f"{self.base}/notifications/{item.pk}/read/"
        self.assertEqual(self.client.post(url, {}).status_code, 200)
        item.refresh_from_db()
        first = item.read_at
        self.assertEqual(self.client.post(url, {}).status_code, 200)
        item.refresh_from_db()
        self.assertEqual(first, item.read_at)
        Job.objects.filter(pk=job.pk).update(
            result_expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(
            self.client.get(f"{self.base}/reports/jobs/{job.pk}/download/").status_code, 404
        )

    def test_schedule_coalesces_downtime_and_preserves_local_closed_period(self):
        rule = save_rule(
            tenant_id=self.tenant.pk,
            actor=self.user,
            data={
                "name": "Cierre mensual",
                "kind": "report",
                "frequency": "monthly",
                "hour": 9,
                "enabled": True,
                "options": {"file_format": "xlsx", "currency": "ARS", "kind": "summary"},
            },
        )
        from datetime import UTC, datetime

        due = datetime(2026, 10, 1, 12, tzinfo=UTC)
        AutomationRule.objects.filter(pk=rule.pk).update(next_run_at=due - timedelta(days=60))
        self.assertEqual(schedule_due(now=due), 1)
        self.assertEqual(schedule_due(now=due), 0)
        job = Job.objects.get(rule=rule)
        self.assertEqual(job.payload["date_from"], "2026-09-01")
        self.assertEqual(job.payload["date_to"], "2026-09-30")

    def test_internal_reminders_require_optin_respect_due_dates_and_do_not_send_email(self):
        from django.core import mail

        mail.outbox = []
        preferences = BusinessSettings.objects.create(
            tenant=self.tenant, payment_reminders_enabled=False
        )
        invoice = issue_invoice(
            tenant=self.tenant,
            invoice_id=self.draft(due_date=timezone.localdate() - timedelta(days=1)).pk,
            actor=self.user,
        )
        rule = save_rule(
            tenant_id=self.tenant.pk,
            actor=self.user,
            data={
                "name": "Avisos internos",
                "kind": "reminders",
                "frequency": "daily",
                "hour": 9,
                "enabled": True,
            },
        )

        def run(key):
            Job.objects.create(
                tenant=self.tenant,
                requested_by=self.user,
                rule=rule,
                kind="reminders",
                dedupe_key=key,
                available_at=timezone.now(),
            )
            self.assertTrue(execute_job(claim_job()))

        run("disabled")
        self.assertEqual(Notification.objects.count(), 0)
        preferences.payment_reminders_enabled = True
        preferences.save()
        run("enabled")
        run("repeat")
        self.assertEqual(Notification.objects.filter(invoice=invoice).count(), 1)
        self.assertEqual(Notification.objects.filter(invoice=self.invoice).count(), 0)
        self.assertEqual(len(mail.outbox), 0)
        record_payment(
            tenant=self.tenant,
            invoice_id=invoice.pk,
            actor=self.user,
            amount="100.00",
            method="cash",
        )
        run("paid")
        self.assertEqual(Notification.objects.count(), 1)

    def test_new_routes_authorization_and_user_selected_options_cannot_escalate(self):
        for role in ["owner", "admin", "accountant", "sales", "viewer"]:
            self.membership.role = role
            self.membership.save()
            self.assertEqual(
                self.client.get(f"{self.base}/automation/rules/").status_code,
                200 if role in {"owner", "admin"} else 403,
            )
            self.assertEqual(
                self.client.get(f"{self.base}/reports/jobs/").status_code,
                200 if role in {"owner", "admin", "accountant"} else 403,
            )
            self.assertEqual(self.client.get(f"{self.base}/notifications/").status_code, 200)
        self.membership.role = "owner"
        self.membership.save()
        response = self.client.post(
            f"{self.base}/automation/rules/",
            {
                "name": "unsafe",
                "kind": "report",
                "frequency": "daily",
                "hour": 99,
                "enabled": True,
                "tenant": "foreign",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        for _ in range(5):
            self.job()
        self.assertEqual(
            self.client.post(f"{self.base}/reports/jobs/", {}, format="json").status_code, 400
        )


class ConcurrentJobs(BillingFixtures, TransactionTestCase):
    def test_two_workers_claim_once_without_waiting_on_the_same_job(self):
        job = request_report(tenant_id=self.tenant.pk, actor=self.user, params={})
        barrier = Barrier(2)

        def claim():
            try:
                barrier.wait(timeout=10)
                result = claim_job()
                return result.pk if result else None
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(lambda _: claim(), range(2)))
        self.assertEqual(result.count(job.pk), 1)
        self.assertEqual(result.count(None), 1)
        self.assertEqual(JobAttempt.objects.count(), 1)
