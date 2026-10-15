"use client";
import { useCallback, useState } from "react";
import { accountSecurityApi } from "@/lib/account-security-api";
import { Alert, Loading, errorMessage, useAsync } from "./business-ui";

export function AccountEmailVerification(){
  const state=useAsync(useCallback(()=>accountSecurityApi.emailStatus(),[]));const [busy,setBusy]=useState(false);const [message,setMessage]=useState("");const [error,setError]=useState("");
  async function send(){setBusy(true);setMessage("");setError("");try{setMessage((await accountSecurityApi.requestEmailVerification()).detail);}catch(error){setError(errorMessage(error));}finally{setBusy(false);}}
  return <section className="panel p-6 mb-6" aria-label="Verificación de correo"><h2 className="text-lg font-semibold mb-3">Correo electrónico</h2>{state.loading?<Loading/>:state.error?<Alert>{state.error}</Alert>:state.data&&<><p className="mb-3">{state.data.email} · <strong>{state.data.verified?"Correo verificado":"Correo sin verificar"}</strong></p><p className="text-sm text-slate-600 mb-4">La verificación confirma que podés recibir mensajes en esta dirección. El enlace vence en 24 horas y se usa una sola vez. Solicitar otro invalida el anterior.</p><div className="row-actions">{!state.data.verified&&<button className="button" disabled={busy} onClick={()=>void send()}>{busy?"Enviando…":"Enviar enlace de verificación"}</button>}<button className="button secondary" disabled={busy||state.loading} onClick={state.refresh}>Actualizar estado del correo</button></div></>}{error&&<Alert>{error}</Alert>}{message&&<p className="notice-success mt-4" role="status">{message}</p>}</section>;
}
