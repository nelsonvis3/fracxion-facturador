import json
from pathlib import Path
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import override_settings
from rest_framework.test import APIClient
from tenancy.models import Tenant, Membership
from customers.models import Customer
from catalog.models import Product
from billing.services import create_invoice_draft, issue_invoice, record_payment

assert settings.DATABASES['default']['NAME']=='test_facturador_e2e'
assert str(settings.DATABASES['default']['PORT'])=='55439'
from uuid import uuid4
suffix=uuid4().hex[:8]
t=Tenant.objects.create(name='Role audit synthetic',slug=f'role-audit-{suffix}')
other=Tenant.objects.create(name='Foreign role audit synthetic',slug=f'foreign-role-audit-{suffix}')
customer=Customer.objects.create(tenant=t,name='Role audit customer')
foreign_customer=Customer.objects.create(tenant=other,name='Foreign customer')
product=Product.objects.create(tenant=t,name='Role audit product',unit_price='100.00',tax_rate='0.00')
foreign_product=Product.objects.create(tenant=other,name='Foreign product',unit_price='100.00',tax_rate='0.00')
users={}; members={}; results={'checks':[]}
for role in Membership.Role.values:
 u=get_user_model().objects.create_user(email=f'{role}.{suffix}@role-audit.example')
 users[role]=u;members[role]=Membership.objects.create(tenant=t,user=u,role=role)
nonmember=get_user_model().objects.create_user(email=f'nonmember.{suffix}@role-audit.example')
owner=users['owner']
def draft():return create_invoice_draft(tenant=t,actor=owner,customer_id=customer.pk,currency='ARS',lines=[{'product':product.pk,'quantity':'1'}])
invoice=issue_invoice(tenant=t,invoice_id=draft().pk,actor=owner)
payment=record_payment(tenant=t,invoice_id=invoice.pk,actor=owner,method='cash',amount='10')
client=APIClient()
base=f'/api/tenants/{t.pk}'
def check(name,method,url,expected,data=None):
 r=getattr(client,method)(url,data,format='json') if data is not None else getattr(client,method)(url)
 results['checks'].append({'case':name,'method':method,'path':url,'expected':expected,'actual':r.status_code,'ok':r.status_code==expected})
with override_settings(ALLOWED_HOSTS=['testserver']):
 for role,u in users.items():
  client.force_authenticate(u)
  for resource in ['customers','products','invoices','payments','audit-events']:
   check(f'{role}/read/{resource}','get',f'{base}/{resource}/',403 if resource=='audit-events' and role not in ['owner','admin'] else 200)
  check(f'{role}/create/customer','post',f'{base}/customers/',201 if role in ['owner','admin'] else 403,{'name':f'Synthetic {role}'})
  check(f'{role}/create/product','post',f'{base}/products/',201 if role in ['owner','admin'] else 403,{'name':f'Synthetic {role}','unit_price':'1.00','tax_rate':'0.00','currency':'ARS','product_type':'service','unit':'unit'})
  check(f'{role}/create/draft','post',f'{base}/invoices/',201 if role in ['owner','admin'] else 403,{'customer':str(customer.pk),'currency':'ARS','lines':[{'product':str(product.pk),'quantity':'1'}]})
  check(f'{role}/create/payment','post',f'{base}/payments/',201 if role in ['owner','admin','accountant'] else 403,{'invoice':str(invoice.pk),'amount':'1.00','method':'cash'})
  if role not in ['owner','admin']:
   check(f'{role}/reverse','post',f'{base}/payments/{payment.pk}/reverse/',403,{'reason':'Synthetic denied'})
   check(f'{role}/issue','post',f'{base}/invoices/{invoice.pk}/issue/',403,{})
 for condition in ['anonymous','no-membership','inactive-membership','inactive-tenant','inactive-user']:
  client.force_authenticate(None if condition=='anonymous' else nonmember if condition=='no-membership' else owner)
  if condition=='inactive-membership':members['owner'].is_active=False;members['owner'].save()
  if condition=='inactive-tenant':t.is_active=False;t.save()
  if condition=='inactive-user':owner.is_active=False;owner.save()
  for resource in ['customers','products','invoices','payments','audit-events']:
   check(f'{condition}/{resource}','get',f'{base}/{resource}/',401 if condition=='anonymous' else 403)
  members['owner'].is_active=True;members['owner'].save();t.is_active=True;t.save();owner.is_active=True;owner.save()
 client.force_authenticate(owner)
 check('foreign-tenant','get',f'/api/tenants/{other.pk}/customers/',403)
 check('foreign-id-own-path','get',f'{base}/customers/{foreign_customer.pk}/',404)
 for foreign in ['customer','product']:
  check(f'mixed-{foreign}','post',f'{base}/invoices/',400,{'customer':str(foreign_customer.pk if foreign=='customer' else customer.pk),'currency':'ARS','lines':[{'product':str(foreign_product.pk if foreign=='product' else product.pk),'quantity':'1'}]})
 with connection.cursor() as cur:
  cur.execute("SELECT relname, relrowsecurity FROM pg_class WHERE relname IN ('tenancy_tenant','billing_invoice','billing_payment','customers_customer','catalog_product') ORDER BY relname")
  results['rls']=cur.fetchall()
 results['summary']={'checks':len(results['checks']),'passed':sum(r['ok'] for r in results['checks'])}
Path('/tmp/fracxion-enterprise-audit-20261014/evidence/roles-observations.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({'summary':results['summary'],'failed':[r for r in results['checks'] if not r['ok']],'rls':results['rls']},indent=2))
assert all(r['ok'] for r in results['checks'])
