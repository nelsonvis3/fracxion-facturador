import hashlib,json,subprocess
from pathlib import Path
import psycopg
root=Path('/tmp/fracxion-enterprise-audit-20261014')
source='test_facturador_e2e';target='test_facturador_enterprise_restore'
base=['-h','127.0.0.1','-p','55439','-U','audit']
tables=['accounts_user','tenancy_tenant','tenancy_membership','customers_customer','catalog_product','billing_invoice','billing_invoiceline','billing_payment','billing_paymentreversal','auditlog_auditevent']
def fingerprint(db):
 out={}
 with psycopg.connect(host='127.0.0.1',port=55439,user='audit',dbname=db) as conn:
  for table in tables:
   with conn.cursor() as cur:
    cur.execute(f'SELECT row_to_json(t)::text FROM {table} t ORDER BY id::text')
    rows=[r[0] for r in cur.fetchall()]
    out[table]={'rows':len(rows),'sha256':hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
 return out
before=fingerprint(source)
dump=root/'synthetic.dump'
commands=[['pg_dump',*base,'-Fc','-f',str(dump),source],['createdb',*base,target],['pg_restore',*base,'--no-owner','--exit-on-error','-d',target,str(dump)]]
for cmd in commands: subprocess.run(cmd,check=True)
after=fingerprint(target)
result={'source':source,'target':target,'host':'127.0.0.1','port':55439,'commands':commands,'identical_business_rows':before==after,'source_tables':before,'restored_tables':after,'scope':'Synthetic local restore on PostgreSQL 18.6, not external production backups or disaster recovery.'}
(root/'evidence/restore-observations.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'identical_business_rows':before==after,'tables':len(tables),'rows':sum(v['rows'] for v in before.values())},indent=2))
assert before==after
