"use client";
import { Suspense, useCallback, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Printer } from "lucide-react";
import { canManage, canRecordPayment, dateTime, invoiceApi, invoiceLabel, money } from "@/lib/business-api";
import { useTenant } from "@/components/tenant-workspace";
import { Alert, Loading, PageHeading, errorMessage } from "@/components/business-ui";
import { useAsync } from "@/components/business-ui";
import { PaymentForm } from "@/components/payment-form";
import { PaymentHistory } from "@/components/payment-history";

function InvoiceDetail() {
  const tenant = useTenant();
  const { invoiceId } = useParams<{ invoiceId: string }>();
  const state = useAsync(useCallback(() => invoiceApi.get(tenant.id, invoiceId), [tenant.id, invoiceId]));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [paying, setPaying] = useState(false);
  const [version, setVersion] = useState(0);
  async function issue() {
    if (busy || !window.confirm("¿Emitir este comprobante interno? Los datos quedarán cerrados y se asignará una numeración definitiva.")) return;
    setBusy(true); setError("");
    try { await invoiceApi.issue(tenant.id, invoiceId); state.refresh(); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  if (state.loading) return <Loading />;
  if (state.error || !state.data) return <main className="module-content"><Alert>{state.error || "No se encontró la factura."}</Alert><Link className="button secondary" href={`/dashboard/${tenant.id}/invoices`}>Volver a facturas</Link></main>;
  const invoice = state.data;
  return <main className="module-content"><PageHeading title={invoiceLabel(invoice)} description={`${tenant.name} · Creado el ${dateTime(invoice.created_at)}`}><div className="row-actions no-print"><Link className="button secondary" href={`/dashboard/${tenant.id}/invoices`}>Volver</Link><button className="button secondary" onClick={() => window.print()}><Printer size={16} />Imprimir</button>{invoice.status === "draft" && canManage(tenant.role) && <button className="button" disabled={busy} onClick={() => void issue()}>{busy ? "Emitiendo…" : "Emitir factura interna"}</button>}</div></PageHeading>
    <p className="notice-info">Comprobante de gestión interna sin autorización fiscal de ARCA.</p>{error && <Alert>{error}</Alert>}
    <section className="panel"><div className="p-6"><div className="flex flex-wrap justify-between gap-6"><div><h2 className="text-lg font-semibold">{invoice.customer_name_snapshot}</h2>{invoice.customer_legal_name_snapshot && <p>{invoice.customer_legal_name_snapshot}</p>}<p className="mt-2 text-sm text-slate-500">{invoice.customer_document_type_snapshot.toUpperCase()} {invoice.customer_document_number_snapshot}</p><p className="mt-1 text-sm text-slate-500">{[invoice.customer_address_snapshot, invoice.customer_city_snapshot, invoice.customer_province_snapshot, invoice.customer_postal_code_snapshot, invoice.customer_country_code_snapshot].filter(Boolean).join(", ")}</p><p className="mt-1 text-sm text-slate-500">{invoice.customer_email_snapshot}</p></div><div><span className={`badge ${invoice.status === "issued" ? "active" : "draft"}`}>{invoice.status === "issued" ? "Emitida" : "Borrador"}</span>{invoice.issued_at && <p className="mt-2 text-sm text-slate-500">Emisión: {dateTime(invoice.issued_at)}<br />{invoice.issued_by}</p>}</div></div></div>
      <div className="table-scroll"><table className="data-table"><thead><tr><th>Concepto</th><th>Cantidad</th><th>Precio unitario</th><th>Impuesto</th><th>Total</th></tr></thead><tbody>{invoice.lines.map(line => <tr key={line.id}><td>{line.description_snapshot}<small>{line.sku_snapshot}</small></td><td>{line.quantity} {line.unit_snapshot}</td><td>{money(line.unit_price, invoice.currency)}</td><td>{line.tax_rate}%<small>{money(line.tax_amount, invoice.currency)}</small></td><td>{money(line.total, invoice.currency)}</td></tr>)}</tbody></table></div>
      <div className="invoice-totals"><p><span>Subtotal</span><span>{money(invoice.subtotal, invoice.currency)}</span></p><p><span>Impuestos</span><span>{money(invoice.tax_total, invoice.currency)}</span></p><p><span>Total</span><span>{money(invoice.total, invoice.currency)}</span></p></div>
      {invoice.notes && <div className="border-t border-slate-100 p-6 no-print"><h3 className="mb-2 text-sm font-semibold">Notas internas</h3><p className="whitespace-pre-wrap text-sm text-slate-500">{invoice.notes}</p></div>}
    </section>
    {invoice.status === "issued" && <section className="mt-8 no-print"><div className="module-heading"><div><h2 className="text-xl font-semibold">Cobros del documento</h2><p>Pagado: {money(invoice.paid_total, invoice.currency)} · Saldo: {money(invoice.balance, invoice.currency)}</p></div>{canRecordPayment(tenant.role) && invoice.balance !== "0.00" && <button className="button" onClick={() => setPaying(true)}>Registrar pago</button>}</div><PaymentHistory invoiceId={invoice.id} refreshKey={version} onChanged={state.refresh} /></section>}
    {paying && <PaymentForm invoice={invoice} onClose={() => setPaying(false)} onSaved={() => { setVersion(value => value + 1); state.refresh(); }} />}
  </main>;
}
export default function InvoiceDetailPage() { return <Suspense fallback={<Loading />}><InvoiceDetail /></Suspense>; }
