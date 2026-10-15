"use client";
import { useState, useSyncExternalStore, type FormEvent } from "react";
import Link from "next/link";
import { Alert, Loading, errorMessage } from "@/components/business-ui";
import { accountSecurityApi } from "@/lib/account-security-api";

const subscribe=(notify:()=>void)=>{window.addEventListener("hashchange",notify);return()=>window.removeEventListener("hashchange",notify);};
const snapshot=()=>new URLSearchParams(window.location.hash.slice(1)).get("token")??"";

function VerifyForm({token,onVerified}:{token:string;onVerified:(message:string)=>void}){
  const [busy,setBusy]=useState(false);const [error,setError]=useState("");
  async function submit(event:FormEvent){event.preventDefault();setBusy(true);setError("");try{onVerified((await accountSecurityApi.verifyEmail(token)).detail);}catch(error){setError(errorMessage(error));}finally{setBusy(false);}}
  return <><p className="mb-5 text-slate-600">Confirmá la dirección de correo de este enlace. La acción no inicia una sesión ni cambia tu contraseña.</p>{error&&<Alert>{error}</Alert>}<form onSubmit={submit}><button className="button" disabled={busy}>{busy?"Verificando…":"Confirmar mi correo"}</button></form></>;
}

export default function VerifyEmailPage(){
  const token=useSyncExternalStore(subscribe,snapshot,()=>null);const [success,setSuccess]=useState("");
  return <main className="min-h-screen bg-slate-50"><section className="auth-card"><h1>Verificá tu correo</h1>{success?<p className="notice-success" role="status">{success}</p>:token===null?<Loading/>:token?<VerifyForm token={token} onVerified={message=>{setSuccess(message);window.history.replaceState(null,"","/verify-email");}}/>:<p className="notice-info">Abrí el enlace completo que recibiste por correo. Si venció, solicitá otro desde Seguridad de mi cuenta.</p>}<nav aria-label="Accesos de cuenta" className="mt-6 flex flex-col items-start gap-4"><Link className="text-indigo-700 underline" href="/account/security">Seguridad de mi cuenta</Link><Link className="text-indigo-700 underline" href="/">Ir al inicio de sesión</Link></nav></section></main>;
}
