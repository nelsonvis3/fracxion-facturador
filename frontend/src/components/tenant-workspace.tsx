"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { BarChart3, Bell, Building2, ClipboardList, CreditCard, FileDown, LogOut, Package, ReceiptText, Settings, ShieldCheck, Truck, Users, UsersRound, Workflow } from "lucide-react";
import { canAnalyze } from "@/lib/analytics-api";
import { authApi, tenantApi, type Tenant } from "@/lib/api";
import { canManage } from "@/lib/business-api";
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
export const moduleLinks = [
  { path: "", label: "Resumen", icon: Building2 },
  { path: "/customers", label: "Clientes", icon: Users },
  { path: "/products", label: "Productos y servicios", icon: ClipboardList },
  { path: "/invoices", label: "Facturas internas", icon: ReceiptText },
  { path: "/payments", label: "Pagos", icon: CreditCard },
  { path: "/audit", label: "Auditoría", icon: ShieldCheck },
  { path: "/team", label: "Equipo", icon: UsersRound },
  { path: "/settings", label: "Configuración", icon: Settings },
  { path: "/analytics", label: "Análisis", icon: BarChart3 },
  { path: "/reports", label: "Informes", icon: FileDown },
  { path: "/automation", label: "Automatizaciones", icon: Workflow },
  { path: "/notifications", label: "Notificaciones", icon: Bell },
  { path: "/suppliers", label: "Proveedores", icon: Truck },
  { path: "/inventory", label: "Inventario", icon: Package },
  { path: "/expenses", label: "Gastos", icon: ReceiptText },
  { path: "/purchases", label: "Compras", icon: Truck },
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
  return <TenantContext.Provider key={tenant.id} value={{ tenant, refresh: refreshTenant }}>
    <div className="business-shell">
      <aside className="business-sidebar">
        <Link className="business-brand" href="/dashboard"><ReceiptText size={24} /> Fracxion</Link>
        <p className="business-company">{tenant.name}<span>{tenant.role === "viewer" ? "Solo lectura" : tenant.role === "accountant" ? "Contador" : tenant.role === "sales" ? "Ventas" : tenant.role === "owner" ? "Propietario" : "Administrador"}</span></p>
        <nav aria-label="Módulos de empresa">{moduleLinks.filter(item => canViewModule(tenant.role, item.path)).map(({ path, label, icon: Icon }) => <Link key={path} href={base + path} aria-current={(path === "" ? pathname === base : pathname.startsWith(base + path)) ? "page" : undefined}><Icon size={18} />{label}</Link>)}</nav>
        <Link href="/dashboard" className="company-switch">Cambiar empresa</Link>
      </aside>
      <div className="business-main">
        <div className="business-topbar"><span>{tenant.name}</span><Link className="button secondary" href="/account/security">Seguridad de mi cuenta</Link><button className="button secondary" disabled={loggingOut} onClick={async () => {
          setLoggingOut(true);
          setLogoutError("");
          try { await authApi.logout(() => present("farewell", tenant.name)); }
          catch { setLogoutError("No pudimos cerrar la sesión. Volvé a intentarlo."); setLoggingOut(false); }
        }}><LogOut size={16} />{loggingOut ? "Cerrando sesión…" : "Cerrar sesión"}</button></div>
        {logoutError && <Alert>{logoutError}</Alert>}
        {children}
      </div>
    </div>
  </TenantContext.Provider>;
}
