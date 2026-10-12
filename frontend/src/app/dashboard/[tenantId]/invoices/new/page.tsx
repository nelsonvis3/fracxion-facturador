"use client";
import { useCallback, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";
import { customerApi, type Customer } from "@/lib/api";
import { canManage, invoiceApi, money, productApi, type Product } from "@/lib/business-api";
import { useTenant } from "@/components/tenant-workspace";
import { Alert, PageHeading, errorMessage } from "@/components/business-ui";
import { ResourceSelect } from "@/components/resource-select";

type DraftLine = { key: number; product: Product | null; quantity: string };
export default function NewInvoicePage() {
  const tenant = useTenant();
  const router = useRouter();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [currency, setCurrency] = useState("ARS");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([{ key: 0, product: null, quantity: "1" }]);
  const [nextKey, setNextKey] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const customers = useCallback((search: string, page: number) => customerApi.list(tenant.id, { search, page, is_active: true }), [tenant.id]);
  const products = useCallback((search: string, page: number) => productApi.list(tenant.id, { search, page, is_active: true, currency }), [tenant.id, currency]);
  function update(key: number, change: Partial<DraftLine>) { setLines(current => current.map(line => line.key === key ? { ...line, ...change } : line)); }
  async function save(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    if (!customer || lines.some(line => !line.product)) { setError("Seleccioná un cliente y un producto en cada línea."); return; }
    setError(""); setBusy(true);
    try {
      const invoice = await invoiceApi.create(tenant.id, { customer: customer.id, currency, notes, lines: lines.map(line => ({ product: line.product!.id, quantity: line.quantity })) });
      router.push(`/dashboard/${tenant.id}/invoices/${invoice.id}`);
    } catch (err) { setError(errorMessage(err)); setBusy(false); }
  }
  if (!canManage(tenant.role)) return <main className="module-content"><Alert>Tu rol permite consultar facturas, pero no crear borradores.</Alert></main>;
  return <main className="module-content"><PageHeading title="Nuevo borrador" description="Los precios y los impuestos se toman del catálogo vigente."><Link className="button secondary" href={`/dashboard/${tenant.id}/invoices`}>Volver a facturas</Link></PageHeading>
    <form onSubmit={save}><fieldset disabled={busy}><section className="panel p-6"><div className="form-grid"><ResourceSelect label="Cliente" selected={customer} onSelect={setCustomer} loader={customers} describe={item => `${item.name}${item.document_number ? ` · ${item.document_number}` : ""}`} /><label className="field">Moneda ISO<input className="input" required minLength={3} maxLength={3} value={currency} onChange={event => { setCurrency(event.target.value.toUpperCase()); setLines(current => current.map(line => ({ ...line, product: null }))); }} /><span className="text-xs font-normal text-slate-500">Cambiar la moneda limpia los productos seleccionados.</span></label></div></section>
      <h2 className="my-6 text-lg font-semibold">Líneas del documento</h2>
      <div className="grid gap-4">{lines.map((line, index) => <section className="panel p-6" key={line.key}><div className="mb-4 flex items-center justify-between"><h3 className="font-semibold">Línea {index + 1}</h3><button type="button" className="icon-button" aria-label={`Quitar línea ${index + 1}`} disabled={lines.length === 1} onClick={() => setLines(current => current.filter(item => item.key !== line.key))}><Trash2 size={17} /></button></div><div className="form-grid"><ResourceSelect key={currency} label="Producto" selected={line.product} onSelect={product => update(line.key, { product })} loader={products} describe={product => `${product.name} · ${money(product.unit_price, product.currency)}`} /><label className="field">Cantidad<input className="input" type="number" min="0.001" max="999999999.999" step="0.001" required value={line.quantity} onChange={event => update(line.key, { quantity: event.target.value })} />{line.product && <span className="text-xs font-normal text-slate-500">Precio: {money(line.product.unit_price, line.product.currency)} · Impuesto: {line.product.tax_rate}%</span>}</label></div></section>)}</div>
      <button type="button" className="button secondary mt-4" disabled={lines.length >= 100} onClick={() => { setLines(current => [...current, { key: nextKey, product: null, quantity: "1" }]); setNextKey(value => value + 1); }}>Agregar línea</button>
      <label className="field mt-6">Notas internas<textarea className="input" maxLength={10000} rows={3} value={notes} onChange={event => setNotes(event.target.value)} /></label>
    </fieldset><p className="notice-info">Al guardar verás los totales calculados por el servidor. El borrador se conserva como registro y podrá emitirse una sola vez.</p>{error && <Alert>{error}</Alert>}<footer className="form-footer"><button className="button" disabled={busy}>{busy ? "Guardando…" : "Guardar borrador"}</button></footer></form>
  </main>;
}
