"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, LoaderCircle, ReceiptText } from "lucide-react";
import { ApiError, authApi, type RegistrationPayload } from "@/lib/api";
import { Alert, errorMessage } from "@/components/business-ui";
import { useSessionTransition } from "@/components/session-transition";

type FieldName = keyof RegistrationPayload;
type FieldErrors = Partial<Record<FieldName, string>>;
const fields: { name: FieldName; label: string; autoComplete: string; type?: string; optional?: boolean; maxLength: number; minLength?: number }[] = [
  { name: "first_name", label: "Nombre", autoComplete: "given-name", maxLength: 150 },
  { name: "last_name", label: "Apellido (opcional)", autoComplete: "family-name", optional: true, maxLength: 150 },
  { name: "company_name", label: "Nombre de tu empresa", autoComplete: "organization", maxLength: 150 },
  { name: "email", label: "Correo electrónico", autoComplete: "email", type: "email", maxLength: 254 },
  { name: "password", label: "Contraseña", autoComplete: "new-password", type: "password", minLength: 8, maxLength: 128 },
  { name: "password_confirm", label: "Confirmá la contraseña", autoComplete: "new-password", type: "password", minLength: 8, maxLength: 128 },
];

export default function RegisterPage() {
  const router = useRouter();
  const present = useSessionTransition();
  const formRef = useRef<HTMLFormElement>(null);
  const [form, setForm] = useState<RegistrationPayload>({ first_name: "", last_name: "", company_name: "", email: "", password: "", password_confirm: "" });
  const [busy, setBusy] = useState(false);
  const [showPasswords, setShowPasswords] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    authApi.currentUser().then(() => { if (active) router.replace("/dashboard"); }).catch(() => {});
    return () => { active = false; };
  }, [router]);

  function showFieldErrors(nextErrors: FieldErrors) {
    setErrors(nextErrors);
    const first = fields.find(field => nextErrors[field.name]);
    if (first) formRef.current?.querySelector<HTMLInputElement>(`[name="${first.name}"]`)?.focus();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError("");
    setErrors({});
    if (form.password !== form.password_confirm) {
      showFieldErrors({ password_confirm: "Las contraseñas no coinciden." });
      return;
    }
    setBusy(true);
    try {
      const response = await authApi.register(form);
      setForm({ first_name: "", last_name: "", company_name: "", email: "", password: "", password_confirm: "" });
      await present("welcome", response.user.first_name || response.tenant.name);
      router.replace(`/dashboard/${response.tenant.id}`);
      router.refresh();
    } catch (err) {
      const nextErrors: FieldErrors = {};
      if (err instanceof ApiError && err.body && typeof err.body === "object") {
        const body = err.body as Record<string, unknown>;
        for (const field of fields) {
          const message = body[field.name];
          if (Array.isArray(message)) nextErrors[field.name] = message.filter(item => typeof item === "string").join(" ");
          else if (typeof message === "string") nextErrors[field.name] = message;
        }
      }
      if (Object.values(nextErrors).some(Boolean)) {
        setError("Revisá los campos indicados para crear tu cuenta.");
        // El fieldset vuelve a habilitarse antes de enfocar el campo inválido.
        requestAnimationFrame(() => showFieldErrors(nextErrors));
      } else setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return <main className="min-h-screen bg-slate-50">
    <section className="auth-card">
      <Link className="business-brand" href="/"><ReceiptText size={23} />Fracxion</Link>
      <h1>Creá tu cuenta</h1>
      <p>Completá tus datos y el nombre de tu empresa para empezar a gestionar clientes, facturas internas y cobros.</p>
      {error && <Alert>{error}</Alert>}
      <form ref={formRef} onSubmit={submit} aria-busy={busy} aria-label="Crear una cuenta">
        <fieldset disabled={busy} className="grid gap-5">
          <legend className="sr-only">Datos de tu cuenta y empresa</legend>
          {fields.map(field => <div className="field" key={field.name}>
            <label htmlFor={`register-${field.name}`}>{field.label}</label>
            <input
              id={`register-${field.name}`}
              name={field.name}
              className="input"
              type={field.type === "password" && showPasswords ? "text" : field.type ?? "text"}
              autoComplete={field.autoComplete}
              required={!field.optional}
              minLength={field.minLength}
              maxLength={field.maxLength}
              value={form[field.name] ?? ""}
              aria-invalid={!!errors[field.name]}
              aria-describedby={errors[field.name] ? `register-${field.name}-error` : field.name === "password" ? "password-help" : undefined}
              onChange={event => {
                setForm(current => ({ ...current, [field.name]: event.target.value }));
                setErrors(current => ({ ...current, [field.name]: undefined }));
              }}
            />
            {field.name === "password" && <span id="password-help" className="text-xs font-normal text-slate-500">Al menos ocho caracteres; evitá contraseñas comunes o parecidas a tus datos.</span>}
            {errors[field.name] && <span id={`register-${field.name}-error`} className="text-sm font-normal text-red-700">{errors[field.name]}</span>}
          </div>)}
          <button type="button" className="flex items-center gap-2 text-sm text-indigo-700" aria-pressed={showPasswords} onClick={() => setShowPasswords(value => !value)}>
            {showPasswords ? <EyeOff size={17} /> : <Eye size={17} />}{showPasswords ? "Ocultar contraseñas" : "Mostrar contraseñas"}
          </button>
          <p>Tu cuenta tendrá acceso de propietario a la empresa que estás creando.</p>
          <button className="button" type="submit">{busy && <LoaderCircle size={18} className="animate-spin" />}{busy ? "Creando cuenta…" : "Crear cuenta"}</button>
        </fieldset>
      </form>
      <Link href="/">Ya tengo una cuenta · Iniciar sesión</Link>
    </section>
  </main>;
}
