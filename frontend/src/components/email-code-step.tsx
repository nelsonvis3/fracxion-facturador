"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { LoaderCircle } from "lucide-react";
import { authApi, type AuthResponse, type MfaRequired } from "@/lib/api";
import { errorMessage } from "@/components/business-ui";

type Props = {
  email: string;
  emailSent: boolean;
  onVerified: (response: AuthResponse | MfaRequired) => Promise<void> | void;
  onBack: () => void;
};

/** Second step of signup and of any login of an account that has not confirmed its email. */
export function EmailCodeStep({ email, emailSent, onVerified, onBack }: Props) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(emailSent ? "" : "No pudimos enviar el correo. Pedí un código nuevo.");
  const [notice, setNotice] = useState("");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => { input.current?.focus(); }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || code.length !== 6) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await authApi.confirmSignupCode(email, code);
      setCode("");
      await onVerified(response);
    } catch (err) {
      setError(errorMessage(err));
      setCode("");
      input.current?.focus();
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { setNotice((await authApi.resendSignupCode(email)).detail); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  return <form onSubmit={submit} aria-busy={busy} aria-label="Confirmar el correo" className="grid gap-4">
    <p className="text-sm text-slate-600">
      Te enviamos un código de 6 dígitos a <strong>{email}</strong>. Vence en 15 minutos; revisá también la carpeta de spam.
    </p>
    <div className="field">
      <label htmlFor="signup-code">Código de verificación</label>
      <input
        ref={input}
        id="signup-code"
        className="input tracking-[0.4em]"
        inputMode="numeric"
        autoComplete="one-time-code"
        pattern="[0-9]{6}"
        maxLength={6}
        required
        value={code}
        disabled={busy}
        onChange={event => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
      />
    </div>
    {error && <div className="notice-error" role="alert">{error}</div>}
    {notice && <p className="text-sm text-slate-600" role="status">{notice}</p>}
    <button className="button" type="submit" disabled={busy || code.length !== 6}>
      {busy && <LoaderCircle size={18} className="animate-spin" />}Confirmar y entrar
    </button>
    <div className="flex flex-wrap justify-between gap-3 text-sm">
      <button type="button" className="text-indigo-700" onClick={resend} disabled={busy}>Enviar otro código</button>
      <button type="button" className="text-indigo-700" onClick={onBack} disabled={busy}>Volver</button>
    </div>
  </form>;
}
