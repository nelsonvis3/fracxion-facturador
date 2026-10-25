"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { Bell, CalendarClock, ChartColumn, FileSpreadsheet, HandCoins, History, House, LogOut, ReceiptText, Settings, ShoppingCart, Tag, Truck, Users, UsersRound, Wallet, Warehouse } from "lucide-react";
import { canAnalyze } from "@/lib/analytics-api";
import { authApi, tenantApi, type Tenant } from "@/lib/api";
import { canManage } from "@/lib/business-api";
import { roleLabels } from "@/lib/enterprise-api";
import { Alert, Loading, useAsync } from "./business-ui";
import { useSessionTransition, useSessionTransitionReady } from "./session-transition";

const TenantContext = createContext<{ tenant: Tenant; refresh: () => Promise<void> } | null>(null);
export function useTenant() {
  const context = useContext(TenantContext);
  if (!context) throw new Error("Se requiere el contexto de empresa.");
  return context.tenant;
}
export function useTenantRefresh() {
  const context = useContext(TenantContext);
  if (!context) throw new Error("Se requiere el contexto de empresa.");
  return context.refresh;
}
// Agrupado por el trabajo diario: vender, comprar, mirar números y administrar la empresa.
export const moduleGroups = [
  { label: "", links: [{ path: "", label: "Resumen", icon: House }] },
  { label: "Ventas", links: [
    { path: "/invoices", label: "Facturas internas", icon: ReceiptText },
    { path: "/payments", label: "Pagos", icon: HandCoins },
    { path: "/customers", label: "Clientes", icon: Users },
    { path: "/products", label: "Productos y servicios", icon: Tag },
  ] },
  { label: "Compras", links: [
    { path: "/purchases", label: "Compras", icon: ShoppingCart },
    { path: "/suppliers", label: "Proveedores", icon: Truck },
    { path: "/expenses", label: "Gastos", icon: Wallet },
    { path: "/inventory", label: "Inventario", icon: Warehouse },
  ] },
  { label: "Números", links: [
    { path: "/analytics", label: "Análisis", icon: ChartColumn },
    { path: "/reports", label: "Informes", icon: FileSpreadsheet },
  ] },
  { label: "Empresa", links: [
    { path: "/team", label: "Equipo", icon: UsersRound },
    { path: "/settings", label: "Configuración", icon: Settings },
    { path: "/automation", label: "Automatizaciones", icon: CalendarClock },
    { path: "/audit", label: "Auditoría", icon: History },
  ] },
];
export const canViewModule = (role: Tenant["role"], path: string) => ["/analytics", "/reports", "/expenses", "/purchases"].includes(path) ? canAnalyze(role) : !["/audit", "/team", "/automation"].includes(path) || canManage(role);
export function TenantWorkspace({ children }: { children: ReactNode }) {
  const { tenantId } = useParams<{ tenantId: string }>();
  return <WorkspaceContent key={tenantId} tenantId={tenantId}>{children}</WorkspaceContent>;
}
function WorkspaceContent({ tenantId, children }: { tenantId: string; children: ReactNode }) {
  const pathname = usePathname();
  const present = useSessionTransition();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const [currentTenant, setCurrentTenant] = useState<Tenant | null | undefined>(undefined);
  const refreshTenant = useCallback(async () => {
    const response = await tenantApi.getMine();
    setCurrentTenant(response.results.find(company => company.id === tenantId) ?? null);
  }, [tenantId]);
  const loader = useCallback(async () => {
    await authApi.currentUser();
    const response = await tenantApi.getMine();
    return response.results.find(tenant => tenant.id === tenantId) ?? null;
  }, [tenantId]);
  const state = useAsync(loader);
  useSessionTransitionReady(!state.loading);
  if (state.loading) return <Loading />;
  const tenant = currentTenant === undefined ? state.data : currentTenant;
  if (state.error || !tenant) return <section className="module-content"><Alert>{state.error || "Esta empresa no está disponible para tu cuenta."}</Alert><Link className="button secondary" href="/dashboard">Mis empresas</Link></section>;
  const base = `/dashboard/${tenant.id}`;
  const current = (path: string) => (path === "" ? pathname === base : pathname.startsWith(base + path)) ? "page" as const : undefined;
  return <TenantContext.Provider key={tenant.id} value={{ tenant, refresh: refreshTenant }}>
    <div className="business-shell">
      <aside className="business-sidebar">
        <Link className="business-brand" href="/dashboard"><ReceiptText size={22} aria-hidden="true" /> Fracxion</Link>
        <nav aria-label="Módulos de empresa">
          {moduleGroups.map(group => {
            const links = group.links.filter(item => canViewModule(tenant.role, item.path));
            if (!links.length) return null;
            return <div className="business-nav-group" key={group.label || "inicio"}>
              {group.label && <p className="business-nav-label">{group.label}</p>}
              {links.map(({ path, label, icon: Icon }) => <Link key={path} href={base + path} aria-current={current(path)}><Icon size={17} aria-hidden="true" />{label}</Link>)}
            </div>;
          })}
        </nav>
        <Link href="/dashboard" className="company-switch">Cambiar empresa</Link>
      </aside>
      <div className="business-main">
        <div className="business-topbar">
          <p className="business-company">{tenant.name}<span>{roleLabels[tenant.role]}</span></p>
          <div className="business-topbar-actions">
            <Link className="icon-link" href={`${base}/notifications`} aria-label="Notificaciones" aria-current={current("/notifications")} title="Notificaciones"><Bell size={18} aria-hidden="true" /></Link>
            <Link className="button secondary" href="/account/security">Seguridad de mi cuenta</Link>
            <button className="button secondary" disabled={loggingOut} onClick={async () => {
              setLoggingOut(true);
              setLogoutError("");
              try { await authApi.logout(() => present("farewell", tenant.name)); }
              catch { setLogoutError("No pudimos cerrar la sesión. Volvé a intentarlo."); setLoggingOut(false); }
            }}><LogOut size={16} aria-hidden="true" />{loggingOut ? "Cerrando sesión…" : "Cerrar sesión"}</button>
          </div>
        </div>
        {logoutError && <Alert>{logoutError}</Alert>}
        {children}
      </div>
    </div>
  </TenantContext.Provider>;
}
