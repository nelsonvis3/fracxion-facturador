from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email, validate_slug
from django.db import IntegrityError, transaction

from tenancy.models import Membership, Tenant


class Command(BaseCommand):
    help = "Crea una empresa y su propietario; pide la contraseña de forma interactiva."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument("--slug", required=True)

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        name = options["name"].strip()
        slug = options["slug"].strip()
        try:
            validate_email(email)
            validate_slug(slug)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        if not name or len(name) > 150 or len(slug) > 100:
            raise CommandError("Revisá el nombre (1–150 caracteres) y el slug (1–100).")
        if Tenant.objects.filter(slug=slug).exists():
            raise CommandError("Ya existe una empresa con ese slug.")
        User = get_user_model()
        user = User.objects.filter(email=email).first()
        if user and not user.is_active:
            raise CommandError("La cuenta está desactivada.")
        if user is None:
            user = User(email=email)
            password = getpass("Contraseña del propietario: ")
            if password != getpass("Confirmá la contraseña: "):
                raise CommandError("Las contraseñas no coinciden.")
            try:
                validate_password(password, user=user)
            except ValidationError as exc:
                raise CommandError(" ".join(exc.messages)) from exc
            user.set_password(password)
        try:
            with transaction.atomic():
                if user.pk is None:
                    user.save()
                tenant = Tenant.objects.create(name=name, slug=slug)
                Membership.objects.create(user=user, tenant=tenant, role=Membership.Role.OWNER)
        except IntegrityError as exc:
            raise CommandError(
                "La cuenta o la empresa se creó concurrentemente; revisá y reintentá."
            ) from exc
        self.stdout.write(
            self.style.SUCCESS(f"Empresa creada: {tenant.pk}. Propietario: {user.email}.")
        )
