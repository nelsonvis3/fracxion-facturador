"use client";

import { useCallback } from "react";
import Link from "next/link";
import { ChevronRight, Plus, ShieldCheck } from "lucide-react";
import { analyticsApi, canAnalyze, type Metrics } from "@/lib/analytics-api";
import { expenseApi } from "@/lib/expense-api";
import { canManage, invoiceApi, invoiceLabel, type Invoice } from "@/lib/business-api";
import { companyDate, enterpriseApi } from "@/lib/enterprise-api";
import { displayDate } from "@/lib/receivables";
import { Alert, Amount, Loading, useAsync } from "@/components/business-ui";
import { useTenant } from "@/components/tenant-workspace";

function variation(now: string, before: string) {
  const previous = Number(before);
  if (!previous) return null;
  const percent = Math.round((Number(now) - previous) / previous * 100);
  return `${percent > 0 ? "+" : ""}${percent} % frente a los días anteriores`;
}

function Ledger({ tenantId }: { tenantId: string }) {
  const loader = useCallback(async () => {
    const settings = await enterpriseApi.settings(tenantId);
    const today = companyDate(settings.timezone);
    return analyticsApi.overview(tenantId, { date_from: `${today.slice(0, 8)}01`, date_to: today, currency: settings.default_currency });
  }, [tenantId]);
  const state = useAsync(loader);
  if (state.loading) return <Loading />;
  if (state.error || !state.data) return <Alert>{state.error}<button className="button secondary" onClick={state.refresh}>Reintentar</button></Alert>;
  const { metrics, previous, filters } = state.data;
  const columns: [string, keyof Metrics, string | null, boolean][] = [
    ["Facturado este mes", "invoiced", variation(metrics.invoiced, previous.metrics.invoiced), false],
    ["Cobrado este mes", "collected", variation(metrics.collected, previous.metrics.collected), false],
    ["Por cobrar", "outstanding", `${metrics.unpaid_count} facturas con saldo`, false],
    ["Vencido", "overdue", Number(metrics.overdue) ? "Requiere seguimiento" : "Nada vencido", Number(metrics.overdue) > 0],
  ];
  return <section className="ledger" aria-label={`Montos desde el ${displayDate(filters.date_from)} en ${filters.currency}`}>
    {columns.map(([label, key, note, debit]) => <div key={key} className={debit ? "ledger-cell debit" : key === "collected" ? "ledger-cell credit" : "ledger-cell"}>
      <p>{label}</p>
      <strong><Amount value={String(metrics[key])} currency={filters.currency} /></strong>
      {note && <span>{note}</span>}
    </div>)}
  </section>;
}

export default function TenantDashboardPage() {
  const tenant = useTenant();
  const analyst = canAnalyze(tenant.role);
  const base = `/dashboard/${tenant.id}`;
  const loader = useCallback(async () => {
    const [counts, overdue, latest, payable] = await Promise.all([
      analyticsApi.counts(tenant.id),
      invoiceApi.list(tenant.id, { receivable: "overdue" }),
      invoiceApi.list(tenant.id, { ordering: "-created_at" }),
      analyst ? expenseApi.list(tenant.id, { payment_status: "unpaid" }) : Promise.resolve(null),
    ]);
    return { counts, overdue: overdue.count, latest: latest.results.slice(0, 6), payable: payable?.count ?? null };
  }, [tenant.id, analyst]);
  const state = useAsync(loader);
  const month = new Intl.DateTimeFormat("es-AR", { month: "long", year: "numeric" }).format(new Date());
  const pending: [number | null, string, string][] = state.data ? [
    [state.data.counts.drafts, state.data.counts.drafts === 1 ? "borrador sin emitir" : "borradores sin emitir", `${base}/invoices`],
    [state.data.overdue, state.data.overdue === 1 ? "factura vencida" : "facturas vencidas", `${base}/invoices`],
    [state.data.payable, state.data.payable === 1 ? "gasto por pagar" : "gastos por pagar", `${base}/expenses`],
  ] : [];
  return (
    <main className="module-content overview">
      <header className="module-heading">
        <div><h1 className="first-letter:uppercase">{month}</h1><p>Lo que facturaste, cobraste y tenés pendiente.</p></div>
        <div className="overview-actions">
          <Link className="button secondary" href={`${base}/invoices`}>Ver facturas</Link>
          {canManage(tenant.role) && <Link className="button" href={`${base}/invoices/new`}><Plus size={17} aria-hidden="true" />Nuevo borrador</Link>}
        </div>
      </header>
      {analyst && <Ledger tenantId={tenant.id} />}
      {state.loading ? <Loading /> : state.error || !state.data ? (
        <Alert>{state.error}<button className="button secondary" onClick={state.refresh}>Reintentar</button></Alert>
      ) : <>
        <section className="records" aria-label="Resumen de registros">
          {([["Clientes activos", state.data.counts.customers, "/customers"], ["Productos activos", state.data.counts.products, "/products"], ["Borradores", state.data.counts.drafts, "/invoices"], ["Facturas emitidas", state.data.counts.issued, "/invoices"]] as const).map(([label, count, path]) =>
            <Link key={label} href={base + path} className="overview-metric"><strong>{count}</strong>{label}</Link>)}
        </section>
        <div className="overview-columns">
          <section className="panel" aria-labelledby="pendientes">
            <h2 id="pendientes">Para atender</h2>
            {pending.some(([count]) => count) ? <ul className="ledger-list">
              {pending.filter(([count]) => count).map(([count, label, href]) => <li key={label}><Link href={href}><span><strong>{count}</strong> {label}</span><ChevronRight size={16} aria-hidden="true" /></Link></li>)}
            </ul> : <p className="overview-empty">Nada pendiente: no hay borradores, facturas vencidas ni gastos sin pagar.</p>}
          </section>
          <section className="panel" aria-labelledby="ultimas">
            <h2 id="ultimas">Últimas facturas</h2>
            {state.data.latest.length ? <ul className="ledger-list">
              {state.data.latest.map((invoice: Invoice) => <li key={invoice.id}><Link href={`${base}/invoices/${invoice.id}`}>
                <span className="min-w-0"><b>{invoiceLabel(invoice)}</b> {invoice.customer_name_snapshot}<small>{displayDate((invoice.issued_at ?? invoice.created_at).slice(0, 10))}</small></span>
                <span className={invoice.receivable_status === "overdue" ? "debit-text" : undefined}><Amount value={invoice.total} currency={invoice.currency} /></span>
              </Link></li>)}
            </ul> : <p className="overview-empty">Todavía no hay facturas. Creá un borrador para empezar.</p>}
          </section>
        </div>
      </>}
      <p className="notice-info"><ShieldCheck size={18} aria-hidden="true" /><span>La numeración de los comprobantes es interna. No incluye autorización fiscal ni integración con ARCA.</span></p>
    </main>
  );
}
