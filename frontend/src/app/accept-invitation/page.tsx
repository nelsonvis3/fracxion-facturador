"use client";
import { useCallback, useState, useSyncExternalStore, type FormEvent } from "react";
import Link from "next/link";
import { authApi, type AuthUser } from "@/lib/api";
import { enterpriseApi, roleLabels } from "@/lib/enterprise-api";
import { Alert, Loading, errorMessage, useAsync } from "@/components/business-ui";
import { EnterpriseField, fieldErrors } from "@/components/enterprise-fields";

function AcceptForm({ token }: { token: string }) {
  const [user, setUser] = useState<AuthUser | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [errors, setErrors] = useState<Record<string, string>>({});
  const state = useAsync(useCallback(async () => {
    const preview = await enterpriseApi.previewInvitation(token);
    const account = await authApi.currentUser().then(value => value.user).catch(() => null);
    setUser(account); return preview;
  }, [token]));
  async function accept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    const form = new FormData(event.currentTarget); setBusy(true); setError(""); setErrors({});
    try {
      const response = await enterpriseApi.acceptInvitation({ token, ...(!user && !state.data?.account_exists ? { first_name: String(form.get("first_name") ?? ""), last_name: String(form.get("last_name") ?? ""), password: String(form.get("password") ?? ""), password_confirm: String(form.get("password_confirm") ?? "") } : {}) });
      window.history.replaceState(null, "", "/accept-invitation"); window.location.replace(`/dashboard/${response.tenant.id}`);
    } catch (err) { setError(errorMessage(err)); setErrors(fieldErrors(err)); setBusy(false); }
  }
  if (state.loading) return <Loading />;
  if (state.error || !state.data) return <Alert>{state.error || "No se encontró la invitación."}</Alert>;
  const invitation = state.data;
  const matching = user?.email.toLowerCase() === invitation.email.toLowerCase();
  return <><h1 className="mb-3 text-2xl font-semibold">Unite a {invitation.company_name}</h1><p className="mb-5 text-slate-600">Invitación para {invitation.email} · {roleLabels[invitation.role]}</p>{error && <Alert>{error}</Alert>}{user && !matching ? <Alert>La sesión actual corresponde a otra cuenta. Cerrá esa sesión e iniciá sesión con {invitation.email} para aceptar.</Alert> : invitation.account_exists && !user ? <p className="notice-info">Iniciá sesión con {invitation.email} y volvé a abrir este enlace para aceptar la invitación.</p> : <form onSubmit={accept} aria-label="Aceptar invitación"><fieldset disabled={busy} className="grid gap-4">{!user && <><EnterpriseField id="accept-name" label="Nombre *" error={errors.first_name}><input className="input" id="accept-name" name="first_name" autoComplete="given-name" required maxLength={150} /></EnterpriseField><EnterpriseField id="accept-lastname" label="Apellido"><input className="input" id="accept-lastname" name="last_name" autoComplete="family-name" maxLength={150} /></EnterpriseField><EnterpriseField id="accept-password" label="Contraseña *" error={errors.password}><input className="input" id="accept-password" name="password" type="password" autoComplete="new-password" required minLength={8} maxLength={128} /></EnterpriseField><EnterpriseField id="accept-confirm" label="Confirmá la contraseña *" error={errors.password_confirm}><input className="input" id="accept-confirm" name="password_confirm" type="password" autoComplete="new-password" required minLength={8} maxLength={128} /></EnterpriseField></>}<button className="button mt-2" disabled={busy}>{busy ? "Aceptando…" : "Aceptar invitación"}</button></fieldset></form>}<Link className="mt-6 inline-block text-indigo-700 underline" href="/">Ir al inicio de sesión</Link></>;
}

const subscribeHash = (onChange: () => void) => { window.addEventListener("hashchange", onChange); return () => window.removeEventListener("hashchange", onChange); };
const tokenSnapshot = () => new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
export default function AcceptInvitationPage() {
  const token = useSyncExternalStore(subscribeHash, tokenSnapshot, () => null);
  return <main className="mx-auto my-12 w-[calc(100%-2rem)] max-w-xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">{token === null ? <Loading /> : token ? <AcceptForm token={token} /> : <><h1 className="mb-4 text-2xl font-semibold">Invitación de equipo</h1><p>Para continuar, abrí el enlace completo que recibiste por correo.</p><Link className="mt-4 inline-block text-indigo-700 underline" href="/">Iniciar sesión</Link></>}</main>;
}
