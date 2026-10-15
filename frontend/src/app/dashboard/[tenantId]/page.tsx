"use client";

import { useCallback } from "react";
import Link from "next/link";
import { ArrowUpRight, ClipboardList, FilePenLine, Plus, ReceiptText, ShieldCheck, Users } from "lucide-react";
import { analyticsApi } from "@/lib/analytics-api";
import { Alert, Loading, PageHeading, useAsync } from "@/components/business-ui";
import { canViewModule, moduleLinks, useTenant } from "@/components/tenant-workspace";
import { canManage } from "@/lib/business-api";

const moduleDescriptions: Record<string, string> = {
  "/customers": "Datos de contacto y perfiles de tus clientes.",
  "/products": "Tu catálogo, precios e impuestos.",
  "/invoices": "Borradores y comprobantes internos.",
  "/payments": "Cobros, saldos y reversiones.",
  "/audit": "El historial de cambios de tu empresa.",
  "/team": "Miembros, roles e invitaciones de acceso.",
  "/settings": "Información comercial y preferencias por empresa.",
  "/analytics": "Facturación, cobros y saldos por período y moneda.",
  "/reports": "Informes filtrados, archivos privados e historial de generación.",
  "/automation": "Programación de informes y alertas internas de vencimiento.",
  "/notifications": "Avisos de tu empresa y resultados de tus tareas.",
  "/suppliers": "Contacto, identificación comercial y estado de proveedores.",
  "/inventory": "Existencias, entradas, salidas, ajustes y reversiones.",
  "/purchases": "Pedidos a proveedores y recepciones parciales de productos o servicios.",
  "/expenses": "Obligaciones registradas, pagos y cuentas por pagar.",
};

export default function TenantDashboardPage() {
  const tenant = useTenant();
  const loader = useCallback(async () => {
    const counts = await analyticsApi.counts(tenant.id);
    return [
      { label: "Clientes activos", count: counts.customers, icon: Users, description: "Disponibles para facturar" },
      { label: "Productos activos", count: counts.products, icon: ClipboardList, description: "Productos y servicios del catálogo" },
      { label: "Borradores", count: counts.drafts, icon: FilePenLine, description: "Comprobantes pendientes de emisión" },
      { label: "Facturas emitidas", count: counts.issued, icon: ReceiptText, description: "Comprobantes con numeración interna" },
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
          {moduleLinks.filter(item => item.path && canViewModule(tenant.role, item.path)).map(({ path, label, icon: Icon }) => (
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
