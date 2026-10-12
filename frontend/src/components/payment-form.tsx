"use client";
import { useCallback, useState, type FormEvent } from "react";
import Link from "next/link";
import { invoiceApi, money, paymentApi, type Invoice, type PaymentMethod } from "@/lib/business-api";
import { useTenant } from "./tenant-workspace";
import { Alert, Modal, errorMessage } from "./business-ui";
import { ResourceSelect } from "./resource-select";

const methods: Record<PaymentMethod, string> = { cash: "Efectivo", bank_transfer: "Transferencia bancaria", debit_card: "Tarjeta de débito", credit_card: "Tarjeta de crédito", digital_wallet: "Billetera virtual", check: "Cheque", other: "Otro" };

export function PaymentForm({ invoice: initial, onClose, onSaved }: { invoice?: Invoice; onClose: () => void; onSaved: () => void }) {
  const tenant = useTenant();
  const [invoice, setInvoice] = useState<Invoice | null>(initial ?? null);
  const [method, setMethod] = useState<PaymentMethod>("cash");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [receivedAt, setReceivedAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const invoices = useCallback((search: string, page: number) => invoiceApi.list(tenant.id, { status: "issued", search, page }), [tenant.id]);
  async function save(event: FormEvent) {
    event.preventDefault(); if (busy || !invoice) return;
    setBusy(true); setError("");
    try {
      await paymentApi.create(tenant.id, { invoice: invoice.id, method, amount, external_reference: reference.trim(), notes, ...(receivedAt ? { received_at: new Date(receivedAt).toISOString() } : {}) });
      onSaved(); onClose();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <Modal title="Registrar pago" busy={busy} onClose={onClose}><form onSubmit={save}>{error && <Alert>{error}</Alert>}<fieldset className="form-grid" disabled={busy}>
    <div className="full">{initial ? <p className="notice-info">Interna #{initial.internal_number} · {initial.customer_name_snapshot}<br />Saldo: {money(initial.balance, initial.currency)}</p> : <ResourceSelect label="Factura emitida" selected={invoice} onSelect={item => { setInvoice(item); setAmount(""); }} loader={invoices} describe={item => `#${item.internal_number} · ${item.customer_name_snapshot} · Saldo ${money(item.balance, item.currency)}`} emptyMessage={<><p>No hay facturas emitidas en esta empresa. Los borradores deben emitirse desde Facturas por un propietario o administrador antes de registrar un pago.</p><Link className="button secondary mt-3" href={`/dashboard/${tenant.id}/invoices`} onClick={onClose}>Ver facturas</Link></>} />}</div>
    <label className="field">Importe {invoice ? `(${invoice.currency})` : ""} *<input autoFocus={!!initial} className="input" type="number" min="0.01" step="0.01" max={invoice?.balance ?? "99999999999999.99"} required value={amount} onChange={event => setAmount(event.target.value)} /></label>
    <label className="field">Método<select className="input" value={method} onChange={event => setMethod(event.target.value as PaymentMethod)}>{Object.entries(methods).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label className="field">Referencia externa<input className="input" maxLength={120} value={reference} onChange={event => setReference(event.target.value)} /><span className="text-xs font-normal text-slate-500">Una referencia no puede repetirse para el mismo método.</span></label>
    <label className="field">Fecha de recepción<input className="input" type="datetime-local" value={receivedAt} onChange={event => setReceivedAt(event.target.value)} /><span className="text-xs font-normal text-slate-500">Opcional. Se interpreta en la zona horaria de tu dispositivo.</span></label>
    <label className="field full">Notas<textarea className="input" rows={3} maxLength={10000} value={notes} onChange={event => setNotes(event.target.value)} /></label>
  </fieldset><footer className="form-footer"><button className="button secondary" type="button" disabled={busy} onClick={onClose}>Cancelar</button><button className="button" disabled={busy || !invoice || invoice.balance === "0.00"}>{busy ? "Registrando…" : "Registrar pago"}</button></footer></form></Modal>;
}
