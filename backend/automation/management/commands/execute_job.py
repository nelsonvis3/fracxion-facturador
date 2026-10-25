from django.core.management.base import BaseCommand, CommandError

from automation.models import Job
from automation.services import execute_job


class Command(BaseCommand):
    help = "Ejecuta únicamente una concesión de trabajo ya adquirida por run_jobs."

    def add_arguments(self, parser):
        parser.add_argument("job_id")
        parser.add_argument("lease_id")

    def handle(self, *args, **options):
        job = Job.objects.filter(
            pk=options["job_id"], lease_id=options["lease_id"], status="running"
        ).first()
        if job is None:
            raise CommandError("La concesión ya no está disponible.")
        success = execute_job(job)
        self.stdout.write(f"{job.pk}: {'succeeded' if success else 'not_completed'}")
