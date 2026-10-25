"use client";
import { useCallback, useState, type FormEvent } from "react";
import Link from "next/link";
import { canManage, dateTime, money, paymentApi, type Payment } from "@/lib/business-api";
import { useTenant } from "./tenant-workspace";
import { Alert, Empty, Loading, Modal, Pagination, errorMessage, useAsync } from "./business-ui";

export function PaymentHistory({ invoiceId, refreshKey = 0, onChanged }: { invoiceId?: string; refreshKey?: number; onChanged?: () => void }) {
  const tenant = useTenant();
  const [page, setPage] = useState(1);
  const state = useAsync(useCallback(() => { void refreshKey; return paymentApi.list(tenant.id, { invoice: invoiceId, page }); }, [tenant.id, invoiceId, page, refreshKey]));
  const [reversing, setReversing] = useState<Payment | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function reverse(event: FormEvent) {
    event.preventDefault(); if (!reversing || busy) return;
    setError(""); setBusy(true);
    try { await paymentApi.reverse(tenant.id, reversing.id, reason); setReversing(null); state.refresh(); onChanged?.(); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <section className="panel">
    {state.loading ? <Loading /> : state.error ? <Alert>{state.error}<button className="button secondary" onClick={state.refresh}>Reintentar</button></Alert> : state.data && <>
      {state.data.results.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Factura / cliente</th><th>Recibido</th><th>Método / referencia</th><th>Importe</th><th>Estado</th>{canManage(tenant.role) && <th>Acciones</th>}</tr></thead><tbody>{state.data.results.map(payment => <tr key={payment.id}><td><Link href={`/dashboard/${tenant.id}/invoices/${payment.invoice}`}>Interna #{payment.invoice_number}</Link><small>{payment.customer_name}</small></td><td>{dateTime(payment.received_at)}<small>{payment.recorded_by || "Usuario eliminado"}</small></td><td>{payment.method_label}<small>{payment.external_reference || "Sin referencia externa"}</small>{payment.notes && <details><summary className="cursor-pointer">Notas</summary><p className="mt-2 whitespace-pre-wrap">{payment.notes}</p></details>}</td><td>{money(payment.amount, payment.currency)}</td><td><span className={`badge ${payment.reversal ? "" : "active"}`}>{payment.reversal ? "Revertido" : "Registrado"}</span>{payment.reversal && <details className="mt-2"><summary className="cursor-pointer">Ver reversión</summary><p className="mt-2 whitespace-pre-wrap">{payment.reversal.reason}</p><small>{dateTime(payment.reversal.occurred_at)} · {payment.reversal.reversed_by}</small></details>}</td>{canManage(tenant.role) && <td>{!payment.reversal && <button className="button secondary" onClick={() => { setReversing(payment); setReason(""); setError(""); }}>Revertir</button>}</td>}</tr>)}</tbody></table></div> : <Empty>No hay pagos registrados.</Empty>}
      <Pagination data={state.data} page={page} setPage={setPage} />
    </>}
    {reversing && <Modal title="Revertir pago" onClose={() => setReversing(null)} busy={busy}><form onSubmit={reverse}><p className="notice-info">La reversión de {money(reversing.amount, reversing.currency)} restaurará ese importe al saldo pendiente. El pago original se conserva.</p>{error && <Alert>{error}</Alert>}<label className="field">Motivo *<textarea className="input" autoFocus required maxLength={2000} rows={4} disabled={busy} value={reason} onChange={event => setReason(event.target.value)} /></label><footer className="form-footer"><button className="button secondary" type="button" disabled={busy} onClick={() => setReversing(null)}>Cancelar</button><button className="button danger" disabled={busy || !reason.trim()}>{busy ? "Revirtiendo…" : "Confirmar reversión"}</button></footer></form></Modal>}
  </section>;
}
