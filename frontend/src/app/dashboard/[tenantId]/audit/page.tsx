"use client";
import { useCallback, useState } from "react";
import { auditApi, canManage, dateTime, type AuditEvent } from "@/lib/business-api";
import { useTenant } from "@/components/tenant-workspace";
import { Alert, Empty, Loading, Modal, PageHeading, Pagination, useAsync } from "@/components/business-ui";

export default function AuditPage() {
  const tenant = useTenant();
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<AuditEvent | null>(null);
  const permitted = canManage(tenant.role);
  const state = useAsync(useCallback(() => permitted ? auditApi.list(tenant.id, { action: action || undefined, entity_type: entity || undefined, page }) : Promise.resolve(null), [tenant.id, permitted, action, entity, page]));
  if (!permitted) return <main className="module-content"><Alert>La auditoría está disponible para propietarios y administradores.</Alert></main>;
  return <main className="module-content"><PageHeading title="Auditoría" description="Historial de operaciones y cambios de tu empresa." /><section className="panel"><div className="filters"><select className="input" aria-label="Acción de auditoría" value={action} onChange={event => { setAction(event.target.value); setPage(1); }}><option value="">Todas las acciones</option><option value="create">Creación</option><option value="update">Modificación</option><option value="deactivate">Desactivación</option><option value="issue">Emisión</option><option value="payment">Pago / reversión</option></select><select className="input" aria-label="Entidad de auditoría" value={entity} onChange={event => { setEntity(event.target.value); setPage(1); }}><option value="">Todas las entidades</option>{["customers.customer", "catalog.product", "billing.invoice", "billing.payment", "billing.payment_reversal"].map(value => <option key={value} value={value}>{value === "customers.customer" ? "Cliente" : value === "catalog.product" ? "Producto" : value === "billing.invoice" ? "Factura" : value === "billing.payment" ? "Pago" : "Reversión"}</option>)}</select></div>
    {state.loading ? <Loading /> : state.error ? <Alert>{state.error}<button className="button secondary" onClick={state.refresh}>Reintentar</button></Alert> : state.data && <>{state.data.results.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Fecha</th><th>Acción</th><th>Usuario</th><th>Registro</th><th>Detalle</th></tr></thead><tbody>{state.data.results.map(event => <tr key={event.id}><td>{dateTime(event.occurred_at)}</td><td>{event.action_label}</td><td>{event.actor || "Sistema / usuario eliminado"}</td><td>{event.entity_type}<small>{event.entity_id}</small></td><td><button className="button secondary" onClick={() => setDetail(event)}>Ver cambios</button></td></tr>)}</tbody></table></div> : <Empty />}<Pagination data={state.data} page={page} setPage={setPage} /></>}
  </section>{detail && <Modal title={detail.action_label} onClose={() => setDetail(null)}><div className="dialog-body"><p className="mb-4 text-sm text-slate-500">{dateTime(detail.occurred_at)} · {detail.actor || "Sistema"}</p><h3 className="mb-2 font-semibold">Cambios registrados</h3><pre className="overflow-auto rounded-lg bg-slate-50 p-4 text-xs">{JSON.stringify(detail.changes, null, 2)}</pre><h3 className="mb-2 mt-5 font-semibold">Contexto</h3><pre className="overflow-auto rounded-lg bg-slate-50 p-4 text-xs">{JSON.stringify(detail.metadata, null, 2)}</pre></div></Modal>}</main>;
}
