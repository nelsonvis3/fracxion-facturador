"use client";
import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { authApi } from "@/lib/api";
import { Alert, Loading, errorMessage } from "@/components/business-ui";

function ResetPasswordForm() {
  const params = useSearchParams();
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    if (password !== confirmation) { setError("Las contraseñas no coinciden."); return; }
    setBusy(true); setError("");
    try { const response = await authApi.confirmPasswordReset({ uid, token, password, password_confirm: confirmation }); setSuccess(response.detail); setPassword(""); setConfirmation(""); window.history.replaceState(null, "", "/reset-password"); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <main className="min-h-screen bg-slate-50"><section className="auth-card"><h1>Elegí tu nueva contraseña</h1>{success ? <p className="notice-info" role="status">{success}</p> : !uid || !token ? <><Alert>El enlace está incompleto. Solicitá uno nuevo.</Alert><Link className="button" href="/forgot-password">Solicitar otro enlace</Link></> : <><p>Usá al menos ocho caracteres y una contraseña difícil de adivinar.</p>{error && <Alert>{error}</Alert>}<form onSubmit={submit}><label className="field">Nueva contraseña<input className="input" type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={password} disabled={busy} onChange={event => setPassword(event.target.value)} /></label><label className="field">Confirmá la contraseña<input className="input" type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={confirmation} disabled={busy} onChange={event => setConfirmation(event.target.value)} /></label><button className="button" disabled={busy}>{busy ? "Guardando…" : "Restablecer contraseña"}</button></form><Link className="mt-4 block text-sm text-indigo-600" href="/forgot-password">Solicitar otro enlace</Link></>}<Link href="/">Volver al inicio de sesión</Link></section></main>;
}
export default function ResetPasswordPage() { return <Suspense fallback={<Loading />}><ResetPasswordForm /></Suspense>; }
