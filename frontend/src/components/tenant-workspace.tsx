"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { Building2, ClipboardList, CreditCard, LogOut, ReceiptText, ShieldCheck, Users } from "lucide-react";
import { authApi, tenantApi, type Tenant } from "@/lib/api";
import { canManage } from "@/lib/business-api";
import { Alert, Loading, useAsync } from "./business-ui";

const TenantContext = createContext<Tenant | null>(null);
export function useTenant() {
  const tenant = useContext(TenantContext);
  if (!tenant) throw new Error("Se requiere el contexto de empresa.");
  return tenant;
}
export const moduleLinks = [
  { path: "", label: "Resumen", icon: Building2 },
  { path: "/customers", label: "Clientes", icon: Users },
  { path: "/products", label: "Productos y servicios", icon: ClipboardList },
  { path: "/invoices", label: "Facturas internas", icon: ReceiptText },
  { path: "/payments", label: "Pagos", icon: CreditCard },
  { path: "/audit", label: "Auditoría", icon: ShieldCheck },
];
export function TenantWorkspace({ children }: { children: ReactNode }) {
  const { tenantId } = useParams<{ tenantId: string }>();
  return <WorkspaceContent key={tenantId} tenantId={tenantId}>{children}</WorkspaceContent>;
}
function WorkspaceContent({ tenantId, children }: { tenantId: string; children: ReactNode }) {
  const pathname = usePathname();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const loader = useCallback(async () => {
    await authApi.currentUser();
    const response = await tenantApi.getMine();
    return response.results.find(tenant => tenant.id === tenantId) ?? null;
  }, [tenantId]);
  const state = useAsync(loader);
  if (state.loading) return <Loading />;
  if (state.error || !state.data) return <section className="module-content"><Alert>{state.error || "Esta empresa no está disponible para tu cuenta."}</Alert><Link className="button secondary" href="/dashboard">Mis empresas</Link></section>;
  const tenant = state.data;
  const base = `/dashboard/${tenant.id}`;
  return <TenantContext.Provider key={tenant.id} value={tenant}>
    <div className="business-shell">
      <aside className="business-sidebar">
        <Link className="business-brand" href="/dashboard"><ReceiptText size={24} /> Fracxion</Link>
        <p className="business-company">{tenant.name}<span>{tenant.role === "viewer" ? "Solo lectura" : tenant.role === "accountant" ? "Contador" : tenant.role === "sales" ? "Ventas" : tenant.role === "owner" ? "Propietario" : "Administrador"}</span></p>
        <nav aria-label="Módulos de empresa">{moduleLinks.filter(item => item.path !== "/audit" || canManage(tenant.role)).map(({ path, label, icon: Icon }) => <Link key={path} href={base + path} aria-current={(path === "" ? pathname === base : pathname.startsWith(base + path)) ? "page" : undefined}><Icon size={18} />{label}</Link>)}</nav>
        <Link href="/dashboard" className="company-switch">Cambiar empresa</Link>
      </aside>
      <div className="business-main">
        <div className="business-topbar"><span>{tenant.name}</span><button className="button secondary" disabled={loggingOut} onClick={async () => {
          setLoggingOut(true);
          setLogoutError("");
          try { await authApi.logout(); }
          catch { setLogoutError("No pudimos cerrar la sesión. Volvé a intentarlo."); setLoggingOut(false); }
        }}><LogOut size={16} />{loggingOut ? "Cerrando sesión…" : "Cerrar sesión"}</button></div>
        {logoutError && <Alert>{logoutError}</Alert>}
        {children}
      </div>
    </div>
  </TenantContext.Provider>;
}
