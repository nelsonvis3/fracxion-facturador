"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  Mail,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { ApiError, authApi, tenantApi } from "@/lib/api";
import { BrandMark } from "@/components/brand-mark";
import { LoginIntro } from "@/components/login-intro";
import { useSessionTransition } from "@/components/session-transition";

export default function LoginPage() {
  const router = useRouter();
  const present = useSessionTransition();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    authApi
      .currentUser()
      .then(() => {
        if (active) {
          router.replace("/dashboard");
        }
      })
      .catch(() => {
        // Una sesión inexistente no impide mostrar el login.
      });

    return () => {
      active = false;
    };
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (loading) return;

    setError("");
    setLoading(true);

    try {
      const response = await authApi.login(email.trim(), password);
      // Clear credentials before showing the successful-access presentation.
      setPassword("");
      setEmail("");
      let name = [response.user.first_name, response.user.last_name].map(value => value.trim()).filter(Boolean).join(" ");
      if (!name) {
        try { name = (await tenantApi.getMine()).results[0]?.name || "tu espacio de trabajo"; }
        catch { name = "tu espacio de trabajo"; }
      }
      await present("welcome", name);
      router.replace("/dashboard");
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setError("El correo o la contraseña no son correctos.");
        } else if (err.status === 403) {
          setError(
            "No se pudo validar la solicitud. Actualizá la página e intentá nuevamente.",
          );
        } else {
          setError(err.message);
        }
      } else {
        setError(
          "No pudimos conectar con el servidor. Intentá nuevamente en unos momentos.",
        );
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <LoginIntro>
    <main className="login-shell min-h-screen">
      <div className="login-layout">
        <section className="login-visual">
          <div className="login-orb login-orb-one" />
          <div className="login-orb login-orb-two" />
          <div className="login-visual-grid" />

          <div className="relative z-10 flex h-full flex-col">
            <Link
              href="/"
              className="brand-lockup w-fit"
              aria-label="Fracxion, inicio"
            >
              <span className="brand-icon" data-login-brand>
                <BrandMark />
              </span>
              <span>Fracxion</span>
            </Link>

            <div className="login-headline auth-enter">
              <div className="eyebrow-pill">
                <Sparkles size={14} />
                <span>Simple por naturaleza</span>
              </div>

              <h1>
                Tu empresa,
                <br />
                <span>en buenas manos.</span>
              </h1>

              <p>
                Organizá tu negocio, gestioná tus facturas y
                seguí tus pagos desde un espacio claro,
                ordenado y fácil de usar.
              </p>
            </div>

            <div className="login-benefits auth-enter">
              <div className="login-benefit">
                <CheckCircle2 size={18} />
                <span>Todo lo importante, en un mismo lugar</span>
              </div>

              <div className="login-benefit">
                <ShieldCheck size={18} />
                <span>Accesos y datos protegidos por empresa</span>
              </div>

              <div className="login-benefit">
                <Sparkles size={18} />
                <span>Menos complejidad, más claridad</span>
              </div>
            </div>

            <div className="login-visual-footer">
              Un espacio de trabajo pensado para vos.
            </div>
          </div>
        </section>

        <section className="login-form-panel">
          <div className="login-form-wrap auth-enter">
            <div className="login-mobile-brand">
              <span className="brand-icon" data-login-brand>
                <BrandMark />
              </span>
              <span>Fracxion</span>
            </div>

            <div className="form-heading">
              <div className="form-icon">
                <LockKeyhole size={23} />
              </div>

              <p className="form-kicker">TU ESPACIO DE TRABAJO</p>
              <h2>Qué bueno verte de nuevo.</h2>
              <p>
                Ingresá tus datos para continuar donde lo dejaste.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="login-form">
              <div className="field-group">
                <label htmlFor="email">Correo electrónico</label>

                <div className="input-shell">
                  <Mail size={18} aria-hidden="true" />

                  <input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    placeholder="nombre@empresa.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                    maxLength={254}
                    disabled={loading}
                  />
                </div>
              </div>

              <div className="field-group">
                <div className="password-label-row">
                  <label htmlFor="password">Contraseña</label>

                  <Link
                    href="/forgot-password"
                    className="forgot-link"
                  >
                    ¿Olvidaste tu contraseña?
                  </Link>
                </div>

                <div className="input-shell">
                  <LockKeyhole size={18} aria-hidden="true" />

                  <input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    placeholder="Tu contraseña"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                    disabled={loading}
                  />

                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-label={
                      showPassword
                        ? "Ocultar contraseña"
                        : "Mostrar contraseña"
                    }
                    aria-pressed={showPassword}
                    disabled={loading}
                  >
                    {showPassword ? (
                      <EyeOff size={18} />
                    ) : (
                      <Eye size={18} />
                    )}
                  </button>
                </div>
              </div>

              {error && (
                <div className="form-error" role="alert">
                  {error}
                </div>
              )}

              <button
                type="submit"
                className="login-submit"
                disabled={loading || !email.trim() || !password}
              >
                {loading ? (
                  <>
                    <LoaderCircle size={19} className="animate-spin" />
                    Ingresando...
                  </>
                ) : (
                  <>
                    Iniciar sesión
                    <ArrowRight size={19} />
                  </>
                )}
              </button>
            </form>

            <p className="mt-6 text-center text-sm text-slate-600">
              ¿Todavía no tenés una cuenta?{" "}
              <Link href="/register" className="font-semibold text-indigo-700 underline underline-offset-4">Crear cuenta</Link>
            </p>

            <div className="security-note">
              <ShieldCheck size={17} />
              <span>Tu acceso está protegido mediante una sesión segura.</span>
            </div>

            <footer className="login-footer">
              <span>Facturador SaaS</span>
              <span className="footer-dot" />
              <span>Gestión más simple</span>
            </footer>
          </div>
        </section>
      </div>
    </main>
    </LoginIntro>
  );
}
