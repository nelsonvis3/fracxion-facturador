import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from time import monotonic

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connection

from automation.models import Job, WorkerHeartbeat
from automation.services import claim_job, schedule_due


class Command(BaseCommand):
    help = "Ejecuta trabajos durables; --once permite procesos supervisados y pruebas aisladas."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--scheduler-only", action="store_true")
        parser.add_argument(
            "--job", help="UUID de un trabajo sintético específico (requiere --once)."
        )

    def handle(self, *args, **options):
        def stop(signum, frame):
            raise KeyboardInterrupt

        previous = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM, stop)
        try:
            return self.run_loop(options)
        finally:
            signal.signal(signal.SIGTERM, previous)

    def run_loop(self, options):
        if connection.vendor != "postgresql":
            raise CommandError("Este worker requiere PostgreSQL.")
        if options["job"] and not options["once"]:
            raise CommandError("--job requiere --once.")
        while True:
            close_old_connections()
            from django.utils import timezone

            def heartbeat():
                WorkerHeartbeat.objects.update_or_create(
                    name=socket.gethostname(), defaults={"seen_at": timezone.now()}
                )

            heartbeat()
            # Delete only expired generated binaries; preserve jobs, attempts and audit.
            Job.objects.filter(result_expires_at__lte=timezone.now(), result__isnull=False).update(
                result=None
            )
            if options["job"]:
                # Pin a single due job without claiming an unrelated request.
                from django.db import transaction
                from django.utils import timezone

                with transaction.atomic():
                    target = Job.objects.filter(pk=options["job"], status="pending").first()
                    if target is None:
                        raise CommandError("Trabajo pendiente no disponible.")
                    if target.available_at > timezone.now():
                        raise CommandError("El trabajo todavía no está disponible.")
                    # claim_job supports a scoped UUID to keep the same locking semantics.
                    job = claim_job(job_id=target.pk)
            else:
                schedule_due()
                job = None if options["scheduler_only"] else claim_job()
            if job:
                # A separate process bounds Python/rendering time, not just SQL time.
                from django.utils import timezone

                child = subprocess.Popen(
                    [
                        sys.executable,
                        str(Path(__file__).resolve().parents[3] / "manage.py"),
                        "execute_job",
                        str(job.pk),
                        str(job.lease_id),
                    ]
                )
                try:
                    deadline = monotonic() + 480
                    while True:
                        try:
                            child.wait(timeout=min(10, max(deadline - monotonic(), 0.01)))
                            break
                        except subprocess.TimeoutExpired:
                            heartbeat()
                            if monotonic() >= deadline:
                                raise
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                    Job.objects.filter(pk=job.pk, lease_id=job.lease_id, status="running").update(
                        lease_until=timezone.now()
                    )
                    self.stderr.write(f"{job.pk}: worker_timeout")
                except KeyboardInterrupt:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                    # A restart reclaims the expired lease; no unfinished result was published.
                    Job.objects.filter(pk=job.pk, lease_id=job.lease_id, status="running").update(
                        lease_until=timezone.now()
                    )
                    return
            if options["once"]:
                break
            if not job:
                time.sleep(2)
