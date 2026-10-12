"use client";

import { useCallback, useState, type FormEvent } from "react";
import { Pencil, Plus } from "lucide-react";
import { canManage, money, productApi, type Product, type ProductPayload } from "@/lib/business-api";
import { useTenant } from "@/components/tenant-workspace";
import { Alert, Empty, Loading, Modal, PageHeading, Pagination, errorMessage, useAsync } from "@/components/business-ui";

const blank = (): ProductPayload => ({ name: "", sku: null, description: "", product_type: "product", unit: "unit", unit_price: "", currency: "ARS", tax_rate: "21.00", is_active: true });
const units = { unit: "Unidad", hour: "Hora", kg: "Kilogramo", liter: "Litro", meter: "Metro", pack: "Paquete" };

export default function ProductsPage() {
  const tenant = useTenant();
  const writable = canManage(tenant.role);
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [status, setStatus] = useState("true");
  const [page, setPage] = useState(1);
  const state = useAsync(useCallback(() => productApi.list(tenant.id, { search: appliedSearch, is_active: status || undefined, page }), [tenant.id, appliedSearch, status, page]));
  const [editing, setEditing] = useState<Product | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function update<K extends keyof ProductPayload>(key: K, value: ProductPayload[K]) { setForm(current => ({ ...current, [key]: value })); }
  function edit(product?: Product) {
    setEditing(product ?? null);
    setForm(product ? { name: product.name, sku: product.sku, description: product.description, product_type: product.product_type, unit: product.unit, unit_price: product.unit_price, currency: product.currency, tax_rate: product.tax_rate, is_active: product.is_active } : blank());
    setError(""); setOpen(true);
  }
  async function save(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError("");
    try {
      const payload = { ...form, name: form.name.trim(), sku: form.sku?.trim() || null, currency: form.currency.toUpperCase() };
      if (editing) await productApi.update(tenant.id, editing.id, payload);
      else await productApi.create(tenant.id, payload);
      setOpen(false); setPage(1); state.refresh();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  async function toggle(product: Product) {
    if (busy || (product.is_active && !window.confirm(`¿Desactivar a "${product.name}"? Se conservará su historial.`))) return;
    setBusy(true); setError("");
    try {
      if (product.is_active) await productApi.deactivate(tenant.id, product.id);
      else await productApi.update(tenant.id, product.id, { is_active: true });
      setPage(1); state.refresh();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <main className="module-content">
    <PageHeading title="Productos y servicios" description="Catálogo, precios e impuestos explícitos por empresa.">{writable && <button className="button" onClick={() => edit()}><Plus size={17} />Nuevo producto</button>}</PageHeading>
    {error && !open && <Alert>{error}</Alert>}
    <section className="panel">
      <form className="filters" onSubmit={event => { event.preventDefault(); setPage(1); setAppliedSearch(search.trim()); }}><input className="input" aria-label="Buscar productos" placeholder="Nombre o SKU" value={search} onChange={event => setSearch(event.target.value)} /><button className="button secondary">Buscar</button><select className="input" aria-label="Estado de productos" value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="true">Activos</option><option value="false">Inactivos</option><option value="">Todos</option></select></form>
      {state.loading ? <Loading /> : state.error ? <Alert>{state.error}<button onClick={state.refresh} className="button secondary">Reintentar</button></Alert> : state.data && <>
        {!state.data.results.length ? <Empty /> : <div className="table-scroll"><table className="data-table"><thead><tr><th>Producto</th><th>Tipo / unidad</th><th>Precio</th><th>Impuesto</th><th>Estado</th>{writable && <th>Acciones</th>}</tr></thead><tbody>{state.data.results.map(product => <tr key={product.id}><td>{product.name}<small>{product.sku || "Sin SKU"}</small></td><td>{product.product_type === "service" ? "Servicio" : "Producto"}<small>{units[product.unit]}</small></td><td>{money(product.unit_price, product.currency)}</td><td>{product.tax_rate}%</td><td><span className={`badge ${product.is_active ? "active" : ""}`}>{product.is_active ? "Activo" : "Inactivo"}</span></td>{writable && <td><div className="row-actions"><button className="icon-button" aria-label={`Editar ${product.name}`} disabled={busy} onClick={() => edit(product)}><Pencil size={16} /></button><button className="button secondary" disabled={busy} onClick={() => void toggle(product)}>{product.is_active ? "Desactivar" : "Reactivar"}</button></div></td>}</tr>)}</tbody></table></div>}
        <Pagination data={state.data} page={page} setPage={setPage} />
      </>}
    </section>
    {open && <Modal title={editing ? "Editar producto" : "Nuevo producto"} onClose={() => setOpen(false)} busy={busy}><form onSubmit={save}>{error && <Alert>{error}</Alert>}<fieldset disabled={busy} className="form-grid">
      <label className="field full">Nombre *<input autoFocus required maxLength={180} className="input" value={form.name} onChange={event => update("name", event.target.value)} /></label>
      <label className="field">SKU<input maxLength={64} className="input" value={form.sku ?? ""} onChange={event => update("sku", event.target.value)} /></label>
      <label className="field">Tipo<select className="input" value={form.product_type} onChange={event => update("product_type", event.target.value as Product["product_type"])}><option value="product">Producto</option><option value="service">Servicio</option></select></label>
      <label className="field">Unidad<select className="input" value={form.unit} onChange={event => update("unit", event.target.value as Product["unit"])}>{Object.entries(units).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label className="field">Moneda ISO *<input className="input" required minLength={3} maxLength={3} placeholder="ARS" value={form.currency} onChange={event => update("currency", event.target.value.toUpperCase())} /></label>
      <label className="field">Precio unitario *<input type="number" min="0" max="999999999999.99" step="0.01" required className="input" value={form.unit_price} onChange={event => update("unit_price", event.target.value)} /></label>
      <label className="field">Impuesto (%) *<input type="number" min="0" max="100" step="0.01" required className="input" value={form.tax_rate} onChange={event => update("tax_rate", event.target.value)} /></label>
      <label className="field full">Descripción<textarea className="input" rows={3} maxLength={10000} value={form.description} onChange={event => update("description", event.target.value)} /></label>
    </fieldset><footer className="form-footer"><button className="button secondary" type="button" disabled={busy} onClick={() => setOpen(false)}>Cancelar</button><button className="button" disabled={busy}>{busy ? "Guardando…" : "Guardar producto"}</button></footer></form></Modal>}
  </main>;
}
