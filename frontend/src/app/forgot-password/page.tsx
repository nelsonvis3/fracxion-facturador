"use client";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { ReceiptText } from "lucide-react";
import { authApi } from "@/lib/api";
import { Alert, errorMessage } from "@/components/business-ui";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    setBusy(true); setError("");
    try { const response = await authApi.requestPasswordReset(email.trim()); setMessage(response.detail); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  return <main className="min-h-screen bg-slate-50"><section className="auth-card"><Link className="business-brand" href="/"><ReceiptText size={23} />Fracxion</Link><h1>Recuperá tu acceso</h1><p>Ingresá tu correo para solicitar un enlace. El enlace vence en una hora.</p>{error && <Alert>{error}</Alert>}{message ? <p className="notice-info" role="status">{message}</p> : <form onSubmit={submit}><label className="field">Correo electrónico<input className="input" autoComplete="email" type="email" required maxLength={254} value={email} disabled={busy} onChange={event => setEmail(event.target.value)} /></label><button className="button" disabled={busy}>{busy ? "Enviando…" : "Enviar instrucciones"}</button></form>}<Link href="/">Volver al inicio de sesión</Link></section></main>;
}
