"use client";

import { useCallback, useState, type FormEvent } from "react";
import { Alert, Loading, errorMessage, useAsync } from "./business-ui";
import { accountSecurityApi } from "@/lib/account-security-api";

export function AccountMFA({ onChanged }: { onChanged: () => void }) {
  const state = useAsync(useCallback(() => accountSecurityApi.mfaStatus(), []));
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState<{ secret: string; uri: string } | null>(null);
  const [codes, setCodes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const action = (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") || "setup";
    setBusy(true); setError(""); setMessage("");
    try {
      if (action === "setup") {
        setSetup(await accountSecurityApi.mfaSetup(password));
        setMessage("Agregá la clave a tu aplicación autenticadora y confirmá con el código de seis dígitos. La configuración vence en diez minutos.");
      } else {
        if (action === "disable" && !window.confirm("¿Desactivar MFA y cerrar los otros accesos?")) return;
        const result = await accountSecurityApi.mfaManage({ current_password: password, code, action: action as "confirm" | "recovery" | "disable" });
        setCodes(result.recovery_codes || []); setSetup(null); setPassword(""); setCode("");
        setMessage(result.detail); state.refresh(); onChanged();
      }
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return <section className="panel mb-6 p-6" aria-labelledby="mfa-heading">
    <h2 id="mfa-heading" className="text-lg font-semibold">Autenticación en dos pasos</h2>
    <p className="my-4 text-sm text-slate-600">Usá una aplicación como un autenticador TOTP. La protección se aplica al acceso de todas tus empresas y al panel administrativo. Cada código se acepta una sola vez; esperá el siguiente si acabás de usarlo.</p>
    {state.loading ? <Loading /> : state.error ? <Alert>{state.error}</Alert> : state.data && <>
      <p className="mb-4">Estado: <strong>{state.data.enabled ? "Activada" : "Desactivada"}</strong>{state.data.enabled && ` · ${state.data.recovery_codes_remaining} códigos de recuperación disponibles`}</p>
      {!state.data.available && <p className="notice-info">El administrador debe configurar el cifrado para habilitar esta opción.</p>}
      {error && <Alert>{error}</Alert>}{message && <p className="notice-info" role="status">{message}</p>}
      {setup && <div className="my-5 rounded-xl border border-slate-300 p-4"><p>En tu autenticador elegí agregar una clave manual: cuenta Fracxion, basada en tiempo, seis dígitos y período de 30 segundos.</p><p className="mt-3 break-all font-mono" aria-label="Clave del autenticador">{setup.secret}</p><p className="mt-3 text-sm">Esta clave es privada. No la compartas ni la pegues en un sitio externo.</p></div>}
      {codes.length > 0 && <div className="my-5 rounded-xl border border-slate-300 p-4"><h3 className="font-semibold">Guardá tus códigos de recuperación</h3><p className="my-3 text-sm">Solo se muestran ahora. Conservá estos códigos fuera de este dispositivo en un lugar seguro. Cada uno sirve una vez para acceder si perdés el autenticador. Los códigos anteriores quedaron invalidados.</p><pre className="overflow-x-auto p-3" aria-label="Códigos de recuperación">{codes.join("\n")}</pre><button className="button secondary mt-3" onClick={() => setCodes([])}>Ya los guardé, ocultar códigos</button></div>}
      {state.data.available && <form onSubmit={submit} aria-label="Administrar MFA"><div className="form-grid">
        <label className="field">Contraseña actual para MFA<input className="input" type="password" autoComplete="current-password" required maxLength={128} value={password} onChange={e => setPassword(e.target.value)} disabled={busy} /></label>
        {(setup || state.data.enabled) && <label className="field">Código MFA o de recuperación<input className="input" type="text" autoComplete="one-time-code" required maxLength={64} value={code} onChange={e => setCode(e.target.value)} disabled={busy} /></label>}
      </div><footer className="form-footer">
        {state.data.enabled ? <><button className="button secondary" value="recovery" disabled={busy}>Renovar códigos de recuperación</button><button className="button danger" value="disable" disabled={busy}>Desactivar MFA</button></> : <button className="button" value={setup ? "confirm" : "setup"} disabled={busy}>{busy ? "Validando…" : setup ? "Confirmar activación MFA" : "Configurar MFA"}</button>}
        {setup && <button className="button secondary" type="button" disabled={busy} onClick={() => { setSetup(null); setCode(""); setPassword(""); setMessage(""); }}>Cancelar configuración</button>}
      </footer></form>}
    </>}
  </section>;
}
