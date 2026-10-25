"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Alert, Empty, Loading, PageHeading, Pagination, errorMessage, useAsync } from "@/components/business-ui";
import { useTenant } from "@/components/tenant-workspace";
import { automationApi } from "@/lib/automation-api";
import { dateTime as displayDateTime } from "@/lib/business-api";
import { canAnalyze } from "@/lib/analytics-api";

export default function NotificationsPage() {
  const tenant = useTenant(); const [page, setPage] = useState(1); const [unread, setUnread] = useState(false); const [error, setError] = useState(""); const [busy, setBusy] = useState("");
  const state = useAsync(useCallback(() => automationApi.notifications(tenant.id, page, unread), [tenant.id, page, unread])); const { refresh } = state;
  useEffect(() => { const timer = window.setInterval(() => { if (document.visibilityState === "visible") refresh(); }, 60000); return () => window.clearInterval(timer); }, [refresh]);
  async function read(id: string) { setError(""); setBusy(id); try { await automationApi.read(tenant.id, id); refresh(); } catch (error) { setError(errorMessage(error)); } finally { setBusy(""); } }
  return <main className="module-content"><PageHeading title="Notificaciones" description="Avisos internos de tu empresa y resultados de tus tareas." />{error && <Alert>{error}</Alert>}<section className="panel"><header className="flex flex-wrap items-center justify-between gap-4 p-6"><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={unread} onChange={event => { setUnread(event.target.checked); setPage(1); }} />Solo no leídas</label><button className="button secondary" onClick={refresh} disabled={state.loading}>Actualizar avisos</button></header>{state.loading && !state.data ? <Loading /> : state.error ? <Alert>{state.error}</Alert> : state.data && <>{state.data.results.length ? <ul className="divide-y divide-slate-200">{state.data.results.map(item => <li key={item.id} className="p-6"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-semibold">{item.title}{!item.read_at && <span className="ml-2 text-xs text-indigo-700">Nueva</span>}</h2><p className="mt-2 text-sm text-slate-600">{item.message}</p><p className="mt-2 text-xs text-slate-500">{displayDateTime(item.created_at)}</p></div>{!item.read_at && <button className="button secondary" disabled={busy === item.id} onClick={() => void read(item.id)}>Marcar como leída</button>}</div>{item.invoice && <Link className="mt-3 inline-block text-sm font-semibold text-indigo-700" href={`/dashboard/${tenant.id}/invoices/${item.invoice}`}>Ver factura interna</Link>}{item.job && canAnalyze(tenant.role) && <Link className="mt-3 inline-block text-sm font-semibold text-indigo-700" href={`/dashboard/${tenant.id}/reports`}>Ver mis informes</Link>}</li>)}</ul> : <Empty>No hay notificaciones para este filtro.</Empty>}<Pagination data={state.data} page={page} setPage={setPage} /></>}</section></main>;
}
