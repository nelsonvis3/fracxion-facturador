import socket
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from automation.models import WorkerHeartbeat


class Command(BaseCommand):
    help = "Comprueba el latido del worker del contenedor actual."

    def handle(self, *args, **options):
        if not WorkerHeartbeat.objects.filter(
            name=socket.gethostname(), seen_at__gte=timezone.now() - timedelta(seconds=30)
        ).exists():
            raise CommandError("Worker sin latido reciente.")
        self.stdout.write("ok")
