"""Datos ficticios; solo acepta el PostgreSQL efímero de esta captura."""
import os
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'backend'))
if os.environ.get('DJANGO_SETTINGS_MODULE') != 'config.e2e_settings':
    raise RuntimeError('Se requiere la configuración E2E.')
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from catalog.models import Product
from customers.models import Customer
from tenancy.models import Membership, Tenant

db = settings.DATABASES['default']
if (db['NAME'], db['HOST'], str(db['PORT'])) != ('test_facturador_e2e', '127.0.0.1', '55435'):
    raise RuntimeError('La captura requiere la base efímera explícita en 55435.')
call_command('migrate', verbosity=0)
tenant, _ = Tenant.objects.get_or_create(id=UUID('00000000-0000-4000-8000-000000000001'), defaults={'name': 'Demo Fracxion', 'slug': 'demo-fracxion-video'})
user, _ = get_user_model().objects.get_or_create(email='owner@demo.example', defaults={'first_name': 'Demo'})
user.set_password('SyntheticVideoPassword2026!')
user.save()
Membership.objects.update_or_create(user=user, tenant=tenant, defaults={'role': 'owner', 'is_active': True})
for name, email in [('Estudio Sur', 'estudio@demo.example'), ('Marina Pérez', 'marina@demo.example'), ('Tienda Norte', 'tienda@demo.example')]:
    Customer.objects.get_or_create(tenant=tenant, name=name, defaults={'email': email, 'city': 'Formosa', 'province': 'Formosa', 'country_code': 'AR', 'postal_code': '3600', 'created_by': user})
for name, price, kind in [('Soporte mensual', '1000.00', 'service'), ('Licencia de gestión', '2500.00', 'product'), ('Configuración inicial', '1500.00', 'service')]:
    Product.objects.get_or_create(tenant=tenant, name=name, defaults={'unit_price': Decimal(price), 'tax_rate': Decimal('21.00'), 'currency': 'ARS', 'product_type': kind, 'unit': 'unit'})
print('Empresa, propietario, tres clientes y tres productos sintéticos preparados.')
