"""Read-only audit of product code; writes synthetic data only in guarded E2E DB."""
import json
from decimal import Decimal
from pathlib import Path

import django

django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext

from auditlog.models import AuditEvent
from billing.models import Payment
from billing.services import create_invoice_draft, issue_invoice, record_payment, get_invoice_balance
from catalog.models import Product
from customers.models import Customer
from tenancy.models import Tenant, Membership

assert settings.DATABASES['default']['NAME'] == 'test_facturador_e2e'
assert str(settings.DATABASES['default']['PORT']) == '55439'
tenant = Tenant.objects.create(name='Enterprise audit probes', slug='enterprise-audit-probes')
user = get_user_model().objects.create_user(email='probe@audit.example', password='SyntheticProbePassword2026!')
member = Membership.objects.create(tenant=tenant, user=user, role='owner')
customer = Customer.objects.create(tenant=tenant, name='Synthetic probe customer')
product = Product.objects.create(tenant=tenant, name='Synthetic probe product', unit_price=Decimal('100'), tax_rate=Decimal('0'), currency='ARS')
results = {'database': settings.DATABASES['default']['NAME'], 'port': settings.DATABASES['default']['PORT'], 'issue_queries': []}
for count in (1,10,100):
    draft = create_invoice_draft(tenant=tenant,customer_id=customer.pk,actor=user,currency='ARS',lines=[{'product':product.pk,'quantity':Decimal('1')}] * count)
    with CaptureQueriesContext(connection) as queries:
        invoice = issue_invoice(tenant=tenant, invoice_id=draft.pk, actor=user)
    results['issue_queries'].append({'lines':count,'queries':len(queries),'product_existence_queries':sum('SELECT 1 AS' in q['sql'] and 'catalog_product' in q['sql'] for q in queries)})
invoice = create_invoice_draft(tenant=tenant,customer_id=customer.pk,actor=user,currency='ARS',lines=[{'product':product.pk,'quantity':Decimal('1')}])
invoice = issue_invoice(tenant=tenant,invoice_id=invoice.pk,actor=user)
for _ in range(2):
    record_payment(tenant=tenant,invoice_id=invoice.pk,actor=user,method='cash',amount='10.00')
results['repeated_payment_without_reference'] = {'payments':Payment.objects.filter(invoice=invoice).count(),'balance':str(get_invoice_balance(invoice))}
with override_settings(ALLOWED_HOSTS=['testserver']):
    client=Client()
    before=AuditEvent.objects.count()
    response=client.post('/api/auth/login/',data=json.dumps({'email':user.email,'password':'SyntheticProbePassword2026!'}),content_type='application/json')
    logout=client.post('/api/auth/logout/')
    results['auth_audit']={'login_http':response.status_code,'logout_http':logout.status_code,'audit_events_delta':AuditEvent.objects.count()-before}
    admin=get_user_model().objects.create_superuser(email='admin@audit.example',password='SyntheticAdminPassword2026!')
    client.force_login(admin)
    before=AuditEvent.objects.count()
    response=client.post(f'/admin/tenancy/membership/{member.pk}/change/',data={'tenant':str(tenant.pk),'user':str(user.pk),'role':'owner','_save':'Save'})
    member.refresh_from_db()
    results['admin_last_owner']={'http':response.status_code,'membership_active':member.is_active,'active_owners':Membership.objects.filter(tenant=tenant,is_active=True,user__is_active=True,role='owner').count(),'business_audit_delta':AuditEvent.objects.count()-before}
    from django.contrib.admin.models import LogEntry
    results['admin_last_owner']['django_admin_log_entries']=LogEntry.objects.filter(object_id=str(member.pk)).count()
print(json.dumps(results,indent=2))
Path('/tmp/fracxion-enterprise-audit-20261014/evidence/probes-results.json').write_text(json.dumps(results,indent=2)+'\n')
