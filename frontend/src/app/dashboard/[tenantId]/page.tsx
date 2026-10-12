"use client";

import { useCallback } from "react";
import Link from "next/link";
import { ArrowUpRight, ClipboardList, FilePenLine, Plus, ReceiptText, ShieldCheck, Users } from "lucide-react";
import { customerApi } from "@/lib/api";
import { invoiceApi, productApi } from "@/lib/business-api";
import { Alert, Loading, PageHeading, useAsync } from "@/components/business-ui";
import { moduleLinks, useTenant } from "@/components/tenant-workspace";
import { canManage } from "@/lib/business-api";

const moduleDescriptions: Record<string, string> = {
  "/customers": "Datos de contacto y perfiles de tus clientes.",
  "/products": "Tu catálogo, precios e impuestos.",
  "/invoices": "Borradores y comprobantes internos.",
  "/payments": "Cobros, saldos y reversiones.",
  "/audit": "El historial de cambios de tu empresa.",
};

export default function TenantDashboardPage() {
  const tenant = useTenant();
  const loader = useCallback(async () => {
    const [customers, products, drafts, issued] = await Promise.all([
      customerApi.list(tenant.id, { is_active: true }),
      productApi.list(tenant.id, { is_active: true }),
      invoiceApi.list(tenant.id, { status: "draft" }),
      invoiceApi.list(tenant.id, { status: "issued" }),
    ]);
    return [
      { label: "Clientes activos", count: customers.count, icon: Users, description: "Disponibles para facturar" },
      { label: "Productos activos", count: products.count, icon: ClipboardList, description: "Productos y servicios del catálogo" },
      { label: "Borradores", count: drafts.count, icon: FilePenLine, description: "Comprobantes pendientes de emisión" },
      { label: "Facturas emitidas", count: issued.count, icon: ReceiptText, description: "Comprobantes con numeración interna" },
    ];
  }, [tenant.id]);
  const state = useAsync(loader);
  return (
    <main className="module-content overview">
      <PageHeading title={tenant.name} description="Tus registros, operaciones y actividad en un mismo espacio.">
        <div className="overview-actions">
          <Link className="button secondary" href={`/dashboard/${tenant.id}/invoices`}>Ver facturas</Link>
          {canManage(tenant.role) && <Link className="button" href={`/dashboard/${tenant.id}/invoices/new`}><Plus size={17} aria-hidden="true" />Nuevo borrador</Link>}
        </div>
      </PageHeading>
      {state.loading ? <Loading /> : state.error ? (
        <Alert>{state.error}<button className="button secondary" onClick={state.refresh}>Reintentar</button></Alert>
      ) : (
        <section className="metrics" aria-label="Resumen de registros">
          {state.data?.map(({ label, count, icon: Icon, description }) => (
            <div className="metric overview-metric" key={label}>
              <div className="overview-metric-top"><span>{label}</span><Icon size={20} aria-hidden="true" /></div>
              <strong>{count}</strong>
              <p>{description}</p>
            </div>
          ))}
        </section>
      )}
      <section aria-labelledby="company-tools-heading">
        <div className="workspace-section-heading"><div><h2 id="company-tools-heading">Tu espacio de gestión</h2><p>Accedé a las herramientas de {tenant.name}.</p></div></div>
        <div className="workspace-modules">
          {moduleLinks.filter(item => item.path && (item.path !== "/audit" || canManage(tenant.role))).map(({ path, label, icon: Icon }) => (
            <Link key={path} className="workspace-module" href={`/dashboard/${tenant.id}${path}`}>
              <div className="workspace-module-top"><span className="workspace-module-icon"><Icon size={22} aria-hidden="true" /></span><ArrowUpRight size={18} aria-hidden="true" /></div>
              <h3>{label}</h3><p>{moduleDescriptions[path]}</p>
            </Link>
          ))}
        </div>
      </section>
      <p className="notice-info"><ShieldCheck size={18} aria-hidden="true" /><span>La numeración de los comprobantes es interna. No incluye autorización fiscal ni integración con ARCA.</span></p>
    </main>
  );
}
