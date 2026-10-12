"use client";
import { useCallback, useState } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";
import { useTenant } from "@/components/tenant-workspace";
import { Alert, Empty, Loading, PageHeading, Pagination, useAsync } from "@/components/business-ui";
import { canManage, dateTime, invoiceApi, invoiceLabel, money } from "@/lib/business-api";

export default function InvoicesPage() {
  const tenant = useTenant();
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const state = useAsync(useCallback(() => invoiceApi.list(tenant.id, { page, status: status || undefined }), [tenant.id, status, page]));
  return <main className="module-content"><PageHeading title="Facturas internas" description="Borradores y comprobantes con numeración interna.">{canManage(tenant.role) && <Link className="button" href={`/dashboard/${tenant.id}/invoices/new`}><Plus size={17} />Nuevo borrador</Link>}</PageHeading>
    <p className="notice-info">Estos documentos no tienen autorización fiscal de ARCA. Los importes y la numeración se calculan en el servidor.</p>
    <section className="panel"><div className="filters"><select className="input" aria-label="Estado de facturas" value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="">Todos los estados</option><option value="draft">Borradores</option><option value="issued">Emitidas</option></select></div>
      {state.loading ? <Loading /> : state.error ? <Alert>{state.error}<button className="button secondary" onClick={state.refresh}>Reintentar</button></Alert> : state.data && <>{state.data.results.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Documento</th><th>Cliente</th><th>Fecha</th><th>Total</th><th>Saldo</th><th>Estado</th></tr></thead><tbody>{state.data.results.map(invoice => <tr key={invoice.id}><td><Link href={`/dashboard/${tenant.id}/invoices/${invoice.id}`}>{invoiceLabel(invoice)}</Link><small>{invoice.id.slice(0, 8)}</small></td><td>{invoice.customer_name_snapshot}</td><td>{dateTime(invoice.created_at)}</td><td>{money(invoice.total, invoice.currency)}</td><td>{invoice.status === "issued" ? money(invoice.balance, invoice.currency) : "Pendiente de emisión"}</td><td><span className={`badge ${invoice.status === "issued" ? "active" : "draft"}`}>{invoice.status === "issued" ? "Emitida" : "Borrador"}</span></td></tr>)}</tbody></table></div> : <Empty />}<Pagination data={state.data} page={page} setPage={setPage} /></>}
    </section></main>;
}
