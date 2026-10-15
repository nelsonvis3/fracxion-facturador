import os
import socket
import subprocess
from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from billing.test_regressions import BillingFixtures

from .models import Job, WorkerHeartbeat
from .services import claim_job, request_report


class WorkerCommands(BillingFixtures, TransactionTestCase):
    def test_health_requires_live_local_heartbeat(self):
        with self.assertRaises(CommandError):
            call_command("job_worker_health", stdout=StringIO())
        WorkerHeartbeat.objects.create(name=socket.gethostname(), seen_at=timezone.now())
        call_command("job_worker_health", stdout=StringIO())
        WorkerHeartbeat.objects.update(seen_at=timezone.now() - timedelta(seconds=60))
        with self.assertRaises(CommandError):
            call_command("job_worker_health", stdout=StringIO())

    def test_registered_execution_rejects_invalid_lease_and_executes_valid_one(self):
        job = request_report(tenant_id=self.tenant.pk, actor=self.user, params={})
        claimed = claim_job()
        with self.assertRaises(CommandError):
            call_command(
                "execute_job",
                str(job.pk),
                "00000000-0000-4000-8000-000000000000",
                stdout=StringIO(),
            )
        call_command("execute_job", str(job.pk), str(claimed.lease_id), stdout=StringIO())
        job.refresh_from_db()
        self.assertEqual(job.status, "succeeded")

    def test_process_timeout_kills_only_owned_child_and_expires_lease(self):
        job = request_report(tenant_id=self.tenant.pk, actor=self.user, params={})
        child = MagicMock()
        child.wait.side_effect = [subprocess.TimeoutExpired("synthetic-job", 480), 0]
        with (
            patch("automation.management.commands.run_jobs.subprocess.Popen", return_value=child),
            patch("automation.management.commands.run_jobs.monotonic", side_effect=[0, 0, 481]),
        ):
            call_command(
                "run_jobs", "--once", "--job", str(job.pk), stdout=StringIO(), stderr=StringIO()
            )
        child.kill.assert_called_once()
        job.refresh_from_db()
        self.assertEqual(job.status, "running")
        self.assertLessEqual(job.lease_until, timezone.now())

    def test_scheduler_only_and_expired_binary_cleanup_preserve_history(self):
        job = request_report(tenant_id=self.tenant.pk, actor=self.user, params={})
        Job.objects.filter(pk=job.pk).update(
            status="succeeded",
            result=b"generated-only",
            result_expires_at=timezone.now() - timedelta(days=1),
        )
        call_command("run_jobs", "--once", "--scheduler-only", stdout=StringIO())
        job.refresh_from_db()
        self.assertIsNone(job.result)
        self.assertEqual(job.status, "succeeded")


class RealWorkerProcess(BillingFixtures, TransactionTestCase):
    def test_separate_process_publishes_committed_job(self):
        job = request_report(
            tenant_id=self.tenant.pk, actor=self.user, params={"file_format": "xlsx"}
        )
        self.assertTrue(connection.settings_dict["NAME"].startswith("test_"))
        with patch.dict(
            os.environ,
            {
                "DB_NAME": connection.settings_dict["NAME"],
                "DJANGO_SETTINGS_MODULE": "config.test_settings",
            },
        ):
            call_command("run_jobs", "--once", "--job", str(job.pk), stdout=StringIO())
        job.refresh_from_db()
        self.assertEqual(job.status, "succeeded")
        self.assertTrue(bytes(job.result).startswith(b"PK"))
