"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowUpRight,
  Building2,
  ClipboardList,
  CreditCard,
  LayoutGrid,
  LoaderCircle,
  LogOut,
  ReceiptText,
  ShieldCheck,
  Users,
} from "lucide-react";

import {
  ApiError,
  authApi,
  tenantApi,
  redirectToLogin,
  type Tenant,
} from "@/lib/api";

type AuthUser = Awaited<
  ReturnType<typeof authApi.currentUser>
>["user"];

const modules = [
  {
    title: "Clientes",
    description: "Organizá los datos de tus clientes.",
    icon: Users,
  },
  {
    title: "Productos y servicios",
    description: "Administrá tu catálogo y precios.",
    icon: ClipboardList,
  },
  {
    title: "Facturación",
    description: "Creá borradores y gestioná comprobantes.",
    icon: ReceiptText,
  },
  {
    title: "Pagos",
    description: "Registrá cobros y consultá saldos.",
    icon: CreditCard,
  },
  {
    title: "Auditoría",
    description: "Consultá el historial de actividad.",
    icon: ShieldCheck,
  },
];

const roleLabels: Record<Tenant["role"], string> = {
  owner: "Propietario",
  admin: "Administrador",
  accountant: "Contador",
  sales: "Ventas",
  viewer: "Solo lectura",
};

export default function DashboardPage() {
  const router = useRouter();

  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState("");

  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantsLoading, setTenantsLoading] = useState(true);
  const [tenantsError, setTenantsError] = useState("");
  const [tenantRequest, setTenantRequest] = useState(0);

  // Verificar la sesión.
  useEffect(() => {
    let active = true;

    async function checkSession() {
      try {
        const response = await authApi.currentUser();

        if (active) {
          setUser(response.user);
        }
      } catch (err: unknown) {
        if (!active) return;

        if (err instanceof ApiError && err.status === 401) {
          redirectToLogin();
          return;
        }

        setError(
          "No pudimos verificar tu sesión. Volvé a intentarlo en unos momentos.",
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void checkSession();

    return () => {
      active = false;
    };
  }, [router]);

  // Obtener las empresas del usuario autenticado.
  useEffect(() => {
    if (!user) return;

    let cancelled = false;

    async function loadTenants() {
      setTenantsLoading(true);
      try {
        const response = await tenantApi.getMine();

        if (!cancelled) {
          setTenants(response.results);
          setTenantsError("");
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setTenantsError(
            err instanceof ApiError
              ? err.message
              : "No se pudieron cargar las empresas.",
          );
        }
      } finally {
        if (!cancelled) {
          setTenantsLoading(false);
        }
      }
    }

    void loadTenants();

    return () => {
      cancelled = true;
    };
  }, [user, tenantRequest]);

  async function handleLogout() {
    if (loggingOut) return;

    setLoggingOut(true);
    setError("");

    try {
      await authApi.logout();
    } catch {
      setError("No se pudo cerrar la sesión. Intentá nuevamente.");
      setLoggingOut(false);
    }
  }

  if (loading) {
    return (
      <main className="dashboard-loading" role="status">
        <span className="workspace-brand-icon"><LoaderCircle size={28} className="animate-spin" aria-hidden="true" /></span>
        <p>Comprobando tu sesión...</p>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="dashboard-loading">
        <p role={error ? "alert" : "status"}>{error || "Redirigiendo al inicio de sesión..."}</p>

        {error && (
          <button
            className="dashboard-retry"
            onClick={() => router.replace("/")}
          >
            Volver al inicio
          </button>
        )}
      </main>
    );
  }

  const displayName =
    user.first_name?.trim() || user.email.split("@")[0];

  return (
    <div className="workspace-shell">
      <aside className="workspace-sidebar">
        <Link href="/dashboard" className="workspace-brand">
          <span className="workspace-brand-icon">
            <ReceiptText size={21} />
          </span>
          <span>Fracxion<span className="workspace-brand-caption">Gestión empresarial</span></span>
        </Link>

        <div className="workspace-section-label">
          ESPACIO DE TRABAJO
        </div>

        <nav className="workspace-nav" aria-label="Espacio de trabajo">
          <Link href="/dashboard" className="workspace-nav-item workspace-nav-active" aria-current="page">
            <LayoutGrid size={18} aria-hidden="true" /><span>Resumen</span>
          </Link>
          <a href="#empresas" className="workspace-nav-item"><Building2 size={18} aria-hidden="true" /><span>Mis empresas</span></a>
          <a href="#herramientas" className="workspace-nav-item"><ClipboardList size={18} aria-hidden="true" /><span>Herramientas</span></a>
        </nav>

        <div className="workspace-sidebar-note">
          <span className="workspace-note-icon">
            <ShieldCheck size={18} />
          </span>

          <p><strong>Un espacio para cada empresa</strong>
            Tus datos están protegidos por empresa y por los permisos
            de cada usuario.
          </p>
        </div>

        <div className="workspace-sidebar-bottom">
          <div className="workspace-avatar">
            {displayName.slice(0, 1).toUpperCase()}
          </div>

          <div className="min-w-0 flex-1">
            <p className="workspace-user-name">{displayName}</p>
            <p className="workspace-user-email">{user.email}</p>
          </div>

          <button
            className="workspace-logout-icon"
            onClick={handleLogout}
            disabled={loggingOut}
            aria-label="Cerrar sesión"
            title="Cerrar sesión"
          >
            {loggingOut ? (
              <LoaderCircle size={18} className="animate-spin" />
            ) : (
              <LogOut size={18} />
            )}
          </button>
        </div>
      </aside>

      <section className="workspace-main">
        <header className="workspace-topbar">
          <span>Tu espacio de trabajo</span>

          <div className="workspace-session-indicator">
            <span />
            Sesión activa
          </div>
        </header>

        <main className="workspace-content auth-enter">
          <div className="workspace-welcome">
            <div>
              <p className="workspace-eyebrow">RESUMEN GENERAL</p>
              <h1>Hola, {displayName}.</h1>
              <p className="workspace-subtitle">
                Elegí una empresa para empezar a trabajar.
              </p>
            </div>

            <div className="workspace-welcome-mark" aria-hidden="true">
              <ReceiptText size={36} />
            </div>
          </div>

          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}

          {/* Empresas del usuario */}
          <section className="workspace-companies" id="empresas" aria-labelledby="companies-heading">
            <div className="workspace-section-heading">
              <div>
                <h2 id="companies-heading">Mis empresas</h2>
                <p>
                  Empresas asociadas a tu cuenta y permisos de acceso.
                </p>
              </div>
              {!tenantsLoading && !tenantsError && <span className="workspace-count">{tenants.length} {tenants.length === 1 ? "empresa" : "empresas"}</span>}
            </div>

            {tenantsLoading ? (
              <div className="workspace-state" role="status">
                <LoaderCircle
                  size={20}
                  className="animate-spin"
                />
                <span>Cargando empresas...</span>
              </div>
            ) : tenantsError ? (
              <div className="workspace-state workspace-state-error" role="alert">
                <p>{tenantsError}</p>
                <button className="dashboard-retry" onClick={() => setTenantRequest(value => value + 1)}>Reintentar</button>
              </div>
            ) : tenants.length === 0 ? (
              <div className="workspace-state workspace-state-empty">
                <Building2 size={28} aria-hidden="true" />
                <h3>
                  No hay empresas asociadas
                </h3>
                <p>
                  Revisá que tu usuario tenga una membresía activa.
                </p>
              </div>
            ) : (
              <div className="workspace-company-grid">
                {tenants.map((tenant) => (
                  <Link key={tenant.id} href={`/dashboard/${tenant.id}`} aria-label={`Abrir el espacio de trabajo de ${tenant.name}`} className="workspace-company-card">
                    <div className="workspace-company-top">
                      <span className="workspace-company-icon"><Building2 size={23} aria-hidden="true" /></span>
                      <span className="workspace-role">{roleLabels[tenant.role]}</span>
                    </div>
                    <h3>{tenant.name}</h3>
                    <p>Tu espacio de gestión</p>
                    <div className="workspace-company-action"><span>Entrar al espacio de trabajo</span><ArrowUpRight size={19} aria-hidden="true" /></div>
                  </Link>
                ))}
              </div>
            )}
          </section>

          {/* Módulos del sistema */}
          <section id="herramientas" aria-labelledby="tools-heading">
          <div className="workspace-section-heading">
            <div>
              <h2 id="tools-heading">Tu sistema de gestión</h2>
              <p>
                Las herramientas disponibles dentro de cada empresa.
              </p>
            </div>
          </div>

          <div className="workspace-modules">
            {modules.map((module, index) => {
              const Icon = module.icon;

              return (
                <article key={module.title} className="workspace-module workspace-module-preview auth-enter" style={{ animationDelay: `${index * 65}ms` }}>
                  <div className="workspace-module-top">
                    <span className="workspace-module-icon">
                      <Icon size={21} aria-hidden="true" />
                    </span>

                  </div>

                  <h3>{module.title}</h3>
                  <p>{module.description}</p>

                  <span className="workspace-module-status">
                    Elegí una empresa para acceder
                  </span>
                </article>
              );
            })}
          </div>
          </section>

          <div className="workspace-footer">
            <ShieldCheck size={17} />
            <span>
              Acceso según tu empresa y tu nivel de permisos.
            </span>
          </div>
        </main>
      </section>
    </div>
  );
}
