"use client";
import { useCallback, useState } from "react";
import Link from "next/link";
import { Plus } from "lucide-react";
import { useTenant } from "@/components/tenant-workspace";
import { Alert, Empty, Loading, PageHeading, Pagination, useAsync } from "@/components/business-ui";
import { canManage, dateTime, invoiceApi, invoiceLabel, money } from "@/lib/business-api";
import { displayDate, receivableLabels } from "@/lib/receivables";

export default function InvoicesPage() {
  const tenant = useTenant();
  const [status, setStatus] = useState("");
  const [receivable, setReceivable] = useState("");
  const [currency, setCurrency] = useState("");
  const [dueFrom, setDueFrom] = useState("");
  const [dueTo, setDueTo] = useState("");
  const [page, setPage] = useState(1);
  const state = useAsync(useCallback(() => invoiceApi.list(tenant.id, { page, status: status || undefined, receivable: receivable || undefined, currency: currency || undefined, due_from: dueFrom || undefined, due_to: dueTo || undefined }), [tenant.id, status, receivable, currency, dueFrom, dueTo, page]));
  return <main className="module-content"><PageHeading title="Facturas internas" description="Borradores y comprobantes con numeración interna.">{canManage(tenant.role) && <Link className="button" href={`/dashboard/${tenant.id}/invoices/new`}><Plus size={17} />Nuevo borrador</Link>}</PageHeading>
    <p className="notice-info">Estos documentos no tienen autorización fiscal de ARCA. Los importes y la numeración se calculan en el servidor.</p>
    <section className="panel"><div className="filters"><select className="input" aria-label="Estado de facturas" value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="">Todos los estados</option><option value="draft">Borradores</option><option value="issued">Emitidas</option></select>
      <select className="input" aria-label="Estado de cobro y vencimiento" value={receivable} onChange={event => { setReceivable(event.target.value); setStatus(""); setPage(1); }}><option value="">Todos los cobros y vencimientos</option><option value="unpaid">Con saldo pendiente</option><option value="overdue">Vencidas</option><option value="due_today">Vencen hoy</option><option value="upcoming">Vencen en los próximos 7 días</option><option value="unscheduled">Sin vencimiento informado</option><option value="paid">Pagadas</option></select>
      <label className="field">Moneda<input className="input" maxLength={3} placeholder="Todas" value={currency} onChange={event => { setCurrency(event.target.value.toUpperCase()); setPage(1); }} /></label>
      <label className="field">Vencimiento desde<input className="input" type="date" value={dueFrom} onChange={event => { setDueFrom(event.target.value); setPage(1); }} /></label>
      <label className="field">Vencimiento hasta<input className="input" type="date" value={dueTo} onChange={event => { setDueTo(event.target.value); setPage(1); }} /></label></div>
      {state.loading ? <Loading /> : state.error ? <Alert>{state.error}<button className="button secondary" onClick={state.refresh}>Reintentar</button></Alert> : state.data && <>{state.data.results.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Documento</th><th>Cliente</th><th>Fecha</th><th>Vencimiento</th><th>Total</th><th>Saldo</th><th>Estado</th></tr></thead><tbody>{state.data.results.map(invoice => <tr key={invoice.id}><td><Link href={`/dashboard/${tenant.id}/invoices/${invoice.id}`}>{invoiceLabel(invoice)}</Link><small>{invoice.id.slice(0, 8)}</small></td><td>{invoice.customer_name_snapshot}</td><td>{dateTime(invoice.created_at)}</td><td>{displayDate(invoice.due_date)}<small>{receivableLabels[invoice.receivable_status]}{invoice.days_overdue ? ` · ${invoice.days_overdue} días de retraso` : ""}</small></td><td>{money(invoice.total, invoice.currency)}</td><td>{invoice.status === "issued" ? money(invoice.balance, invoice.currency) : "Pendiente de emisión"}</td><td><span className={`badge ${invoice.status === "issued" ? "active" : "draft"}`}>{invoice.status === "issued" ? "Emitida" : "Borrador"}</span></td></tr>)}</tbody></table></div> : <Empty />}<Pagination data={state.data} page={page} setPage={setPage} /></>}
    </section></main>;
}
