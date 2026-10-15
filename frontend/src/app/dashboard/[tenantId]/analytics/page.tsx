"use client";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { customerApi, type Customer } from "@/lib/api";
import { money } from "@/lib/business-api";
import { analyticsApi, canAnalyze, type AnalyticsFilters } from "@/lib/analytics-api";
import { companyDate, enterpriseApi, type BusinessSettings } from "@/lib/enterprise-api";
import { displayDate } from "@/lib/receivables";
import { Alert, Empty, Loading, PageHeading, useAsync } from "@/components/business-ui";
import { ResourceSelect } from "@/components/resource-select";
import { useTenant } from "@/components/tenant-workspace";

const agingLabels: Record<string, string> = { not_due: "En plazo o vencen hoy", "1_30": "1–30 días de atraso", "31_60": "31–60 días", "61_90": "61–90 días", over_90: "Más de 90 días", unscheduled: "Sin vencimiento informado" };
function initialFilters(preferences: BusinessSettings): AnalyticsFilters {
  const today = companyDate(preferences.timezone);
  const start = new Date(`${today}T12:00:00Z`); start.setUTCMonth(start.getUTCMonth() - 11, 1);
  return { date_from: start.toISOString().slice(0, 10), date_to: today, currency: preferences.default_currency };
}
function AnalyticsWorkspace({ preferences }: { preferences: BusinessSettings }) {
  const tenant = useTenant();
  const [filters, setFilters] = useState(() => initialFilters(preferences));
  const [draft, setDraft] = useState(filters); const [customer, setCustomer] = useState<Customer | null>(null);
  const customers = useCallback((search: string, page: number) => customerApi.list(tenant.id, { search, page }), [tenant.id]);
  const state = useAsync(useCallback(() => analyticsApi.overview(tenant.id, filters), [tenant.id, filters]));
  const refresh = state.refresh;
  useEffect(() => {
    const refreshVisible = () => { if (document.visibilityState === "visible") refresh(); };
    const changed = (event: Event) => { if ((event as CustomEvent<{tenantId: string}>).detail?.tenantId === tenant.id) refreshVisible(); };
    const interval = window.setInterval(refreshVisible, 60000);
    window.addEventListener("fracxion:business-change", changed); window.addEventListener("focus", refreshVisible);
    return () => { window.clearInterval(interval); window.removeEventListener("fracxion:business-change", changed); window.removeEventListener("focus", refreshVisible); };
  }, [tenant.id, refresh]);
  function apply(event: FormEvent) { event.preventDefault(); setFilters({ ...draft, customer: customer?.id }); }
  const data = state.data; const currency = data?.filters.currency ?? filters.currency;
  // Number is used only for CSS geometry. Monetary text comes from exact backend decimals.
  const max = data ? Math.max(...data.monthly.flatMap(row => [Number(row.invoiced), Number(row.collected)]), 1) : 1;
  return <><section className="panel mb-6 p-6"><form onSubmit={apply} aria-label="Filtros de análisis"><div className="form-grid"><label className="field">Desde<input className="input" type="date" required value={draft.date_from} onChange={event => setDraft({ ...draft, date_from: event.target.value })} /></label><label className="field">Hasta<input className="input" type="date" required min={draft.date_from} value={draft.date_to} onChange={event => setDraft({ ...draft, date_to: event.target.value })} /></label><label className="field">Moneda ISO<input className="input" required minLength={3} maxLength={3} value={draft.currency} onChange={event => setDraft({ ...draft, currency: event.target.value.toUpperCase() })} /></label><div><ResourceSelect label="Cliente" required={false} selected={customer} onSelect={setCustomer} loader={customers} describe={item => item.name} />{customer && <button className="button secondary mt-2" type="button" onClick={() => setCustomer(null)}>Todos los clientes</button>}</div></div><footer className="form-footer"><button className="button" disabled={state.loading}>Aplicar filtros</button><button className="button secondary" type="button" disabled={state.loading} onClick={state.refresh}>Actualizar datos</button></footer></form></section>
    {state.loading && !data ? <Loading /> : state.error ? <Alert>{state.error}<button className="button secondary" onClick={state.refresh}>Reintentar</button></Alert> : data && <>
      {state.loading && <p role="status" className="mb-3 text-sm text-slate-600">Actualizando indicadores…</p>}
      <p className="mb-3 text-sm text-slate-600">Período aplicado: {displayDate(data.filters.date_from)} – {displayDate(data.filters.date_to)}. Refresco cada minuto mientras esta página está visible.</p>
      <p className="notice-info">Facturación por fecha de emisión y cobros efectivos por fecha de recepción. Los saldos son actuales y corresponden a las facturas emitidas en el período elegido. Moneda: {currency}. Zona: {data.timezone}. Referencia de vencimiento: {displayDate(data.as_of)}.</p>
      {data.metrics.overpaid_count > 0 && <Alert>Hay {data.metrics.overpaid_count} documentos con saldo negativo que requieren revisión de integridad.</Alert>}
      <section className="metrics my-6" aria-label="Indicadores financieros">{([
        ["Facturado", data.metrics.invoiced, "Comprobantes internos emitidos"], ["Cobrado efectivo", data.metrics.collected, "Pagos vigentes; excluye reversiones"],
        ["Saldo actual del período", data.metrics.outstanding, "De facturas emitidas en el rango"], ["Saldo vencido del período", data.metrics.overdue, "Con fecha válida y saldo pendiente"],
      ] as const).map(([label, value, help]) => <div className="metric" key={label}><span>{label}</span><strong className="my-2 block break-words text-2xl">{money(value, currency)}</strong><p className="text-sm text-slate-600">{help}</p></div>)}</section>
      <section className="panel mb-6 p-6" aria-label="Comparación de períodos"><h2 className="mb-3 text-lg font-semibold">Comparación con el período anterior</h2><p className="mb-3 text-sm text-slate-600">{displayDate(data.previous.date_from)} – {displayDate(data.previous.date_to)} · misma cantidad de días</p><div className="grid gap-3 sm:grid-cols-2"><p>Facturado anterior: <strong>{money(data.previous.metrics.invoiced, currency)}</strong></p><p>Cobrado anterior: <strong>{money(data.previous.metrics.collected, currency)}</strong></p></div><p className="mt-4 text-sm text-slate-600">{data.metrics.issued_count} documentos emitidos · {data.metrics.unpaid_count} con saldo pendiente · {data.metrics.unscheduled_count} pendientes sin vencimiento informado</p></section>
      <section className="panel mb-6"><header className="p-6"><h2 className="text-lg font-semibold">Evolución mensual</h2><p className="mt-1 text-sm text-slate-600">Cada mes conserva únicamente los días incluidos en el rango.</p></header><div className="table-scroll" role="region" tabIndex={0} aria-label="Facturación y cobros mensuales"><table className="data-table"><thead><tr><th>Mes</th><th>Facturado ({currency})</th><th>Cobrado efectivo ({currency})</th></tr></thead><tbody>{data.monthly.map(row => <tr key={row.month}><th scope="row">{row.month}</th><td>{money(row.invoiced, currency)}<div className="mt-2 h-2 rounded bg-indigo-600" aria-hidden="true" style={{ width: `${Number(row.invoiced) / max * 100}%` }} /></td><td>{money(row.collected, currency)}<div className="mt-2 h-2 rounded bg-emerald-700" aria-hidden="true" style={{ width: `${Number(row.collected) / max * 100}%` }} /></td></tr>)}</tbody></table></div></section>
      <div className="grid items-start gap-6 xl:grid-cols-2"><section className="panel"><h2 className="p-6 text-lg font-semibold">Clientes con mayor facturación</h2>{data.customers.length ? <div className="table-scroll" tabIndex={0} role="region" aria-label="Facturación por cliente"><table className="data-table"><thead><tr><th>Cliente</th><th>Facturado</th></tr></thead><tbody>{data.customers.map(row => <tr key={row.id}><td>{row.name}</td><td>{money(row.invoiced, currency)}</td></tr>)}</tbody></table></div> : <Empty>No hay facturación para este período.</Empty>}</section><section className="panel"><h2 className="p-6 text-lg font-semibold">Antigüedad de saldos</h2><div className="table-scroll" tabIndex={0} role="region" aria-label="Antigüedad de cuentas por cobrar"><table className="data-table"><thead><tr><th>Situación</th><th>Facturas</th><th>Saldo actual</th></tr></thead><tbody>{data.aging.map(row => <tr key={row.bucket}><td>{agingLabels[row.bucket]}</td><td>{row.count}</td><td>{money(row.balance, currency)}</td></tr>)}</tbody></table></div></section><section className="panel"><h2 className="p-6 text-lg font-semibold">Productos y servicios facturados</h2>{data.products.length ? <div className="table-scroll" tabIndex={0} role="region" aria-label="Facturación por producto"><table className="data-table"><thead><tr><th>Descripción histórica</th><th>Cantidad</th><th>Facturado</th></tr></thead><tbody>{data.products.map((row, index) => <tr key={`${row.id}:${index}`}><td>{row.name}<small>{row.sku}</small></td><td>{row.quantity}</td><td>{money(row.invoiced, currency)}</td></tr>)}</tbody></table></div> : <Empty />}</section><section className="panel"><h2 className="p-6 text-lg font-semibold">Medios de cobro</h2>{data.payment_methods.length ? <div className="table-scroll" tabIndex={0} role="region" aria-label="Cobros por medio de pago"><table className="data-table"><thead><tr><th>Medio</th><th>Operaciones</th><th>Cobrado efectivo</th></tr></thead><tbody>{data.payment_methods.map(row => <tr key={row.method}><td>{row.label}</td><td>{row.count}</td><td>{money(row.collected, currency)}</td></tr>)}</tbody></table></div> : <Empty>No hay cobros efectivos para este período.</Empty>}</section></div>
    </>}
  </>;
}

export default function AnalyticsPage() {
  const tenant = useTenant();
  const preferences = useAsync(useCallback(() => canAnalyze(tenant.role) ? enterpriseApi.settings(tenant.id) : Promise.resolve(null), [tenant.id, tenant.role]));
  return <main className="module-content"><PageHeading title="Análisis empresarial" description="Facturación, cobros y cuentas por cobrar, separados por moneda y período." />{!canAnalyze(tenant.role) ? <Alert>Tu rol no permite consultar el análisis financiero.</Alert> : preferences.loading ? <Loading /> : preferences.error ? <Alert>{preferences.error}<button className="button secondary" onClick={preferences.refresh}>Reintentar</button></Alert> : preferences.data && <AnalyticsWorkspace preferences={preferences.data} />}</main>;
}
