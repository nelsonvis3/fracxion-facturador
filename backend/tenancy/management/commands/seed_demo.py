from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from billing.services import create_invoice_draft, issue_invoice, record_payment
from catalog.models import Product
from customers.models import Customer
from tenancy.models import Membership, Tenant

SLUG = "demo-panaderia-la-espiga"
CUSTOMERS = ["Café del Puerto", "Almacén Don Luis", "Hotel Guaraní", "Escuela N.º 12"]
PRODUCTS = [
    ("PAN-001", "Pan francés (kg)", "2800.00"),
    ("FAC-012", "Facturas surtidas (docena)", "6500.00"),
    ("TOR-001", "Torta de cumpleaños", "18000.00"),
    ("PRE-050", "Prepizzas (pack x5)", "5200.00"),
    ("SER-001", "Servicio de catering", "45000.00"),
]
# (customer, [(product, quantity)], paid fraction)
INVOICES = [
    (0, [(0, "12"), (1, "4")], Decimal("1")),
    (1, [(0, "20"), (3, "6")], Decimal("0.5")),
    (2, [(4, "1"), (2, "2")], Decimal("0")),
    (3, [(1, "10")], Decimal("1")),
    (0, [(2, "1"), (1, "2")], Decimal("0")),
]


def demo_user(email):
    """Verified account without a usable password: it only enters through the demo button."""
    User = get_user_model()
    user = User.objects.filter(email=email).first() or User(email=email, first_name="Demo")
    user.set_unusable_password()
    user.is_staff = user.is_superuser = False
    user.verified_email = user.email
    user.email_verified_at = user.email_verified_at or timezone.now()
    user.save()
    return user


class Command(BaseCommand):
    help = "Crea, si no existe, la empresa de demostración de solo lectura (idempotente)."

    @transaction.atomic
    def handle(self, *args, **options):
        email = settings.DEMO_LOGIN_EMAIL
        if not email:
            raise CommandError("Definí DEMO_LOGIN_EMAIL para crear la demo.")
        viewer = demo_user(email)
        owner = demo_user("owner+" + email)
        tenant, created = Tenant.objects.get_or_create(
            slug=SLUG, defaults={"name": "Panadería La Espiga (demo)"}
        )
        Membership.objects.update_or_create(
            tenant=tenant, user=viewer, defaults={"role": Membership.Role.VIEWER, "is_active": True}
        )
        # The owner only exists to issue the sample documents; nobody can sign in with it.
        Membership.objects.update_or_create(
            tenant=tenant, user=owner, defaults={"role": Membership.Role.OWNER, "is_active": True}
        )
        if not created:
            self.stdout.write("La demo ya existía; no se cambiaron sus datos.")
            return
        customers = [
            Customer.objects.create(tenant=tenant, name=name, country_code="AR", postal_code="3600")
            for name in CUSTOMERS
        ]
        products = [
            Product.objects.create(
                tenant=tenant,
                sku=sku,
                name=name,
                unit_price=Decimal(price),
                tax_rate=Decimal("21"),
                currency="ARS",
            )
            for sku, name, price in PRODUCTS
        ]
        for index, (customer, lines, paid) in enumerate(INVOICES):
            draft = create_invoice_draft(
                tenant=tenant,
                customer_id=customers[customer].pk,
                actor=owner,
                currency="ARS",
                lines=[
                    {"product": products[product].pk, "quantity": Decimal(quantity)}
                    for product, quantity in lines
                ],
            )
            invoice = issue_invoice(tenant=tenant, invoice_id=draft.pk, actor=owner)
            if paid:
                record_payment(
                    tenant=tenant,
                    invoice_id=invoice.pk,
                    actor=owner,
                    method="bank_transfer",
                    amount=(invoice.total * paid).quantize(Decimal("0.01")),
                    received_at=timezone.now() - timedelta(days=len(INVOICES) - index),
                )
        create_invoice_draft(
            tenant=tenant,
            customer_id=customers[2].pk,
            actor=owner,
            currency="ARS",
            lines=[{"product": products[4].pk, "quantity": Decimal("2")}],
            notes="Presupuesto para el evento de fin de año.",
        )
        self.stdout.write("Demo creada.")
