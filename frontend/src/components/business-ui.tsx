"use client";

import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { LoaderCircle, X } from "lucide-react";
import { ApiError } from "@/lib/api";
import type { Page } from "@/lib/business-api";

export function useAsync<T>(loader: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError("");
      try { const result = await loader(); if (active) setData(result); }
      catch (err) { if (active) setError(errorMessage(err)); }
      finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [loader, version]);
  const refresh = useCallback(() => setVersion(value => value + 1), []);
  return { data, loading, error, refresh };
}

export function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "No se pudo conectar con el servidor. Intentá nuevamente.";
}
export function Alert({ children }: { children: ReactNode }) { return <div className="notice-error" role="alert">{children}</div>; }
export function Loading() { return <div className="resource-state" role="status"><LoaderCircle className="animate-spin" size={22} /> Cargando información…</div>; }
export function Empty({ children = "No hay registros para los filtros seleccionados." }: { children?: ReactNode }) { return <p className="resource-state">{children}</p>; }
export function PageHeading({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
  return <header className="module-heading"><div><p className="module-eyebrow">GESTIÓN EMPRESARIAL</p><h1>{title}</h1><p>{description}</p></div>{children}</header>;
}
export function Pagination({ data, page, setPage }: { data: Page<unknown>; page: number; setPage: (page: number) => void }) {
  return <footer className="pagination"><span>{data.count} registros · Página {page}</span><div><button className="button secondary" disabled={!data.previous} onClick={() => setPage(page - 1)}>Anterior</button><button className="button secondary" disabled={!data.next} onClick={() => setPage(page + 1)}>Siguiente</button></div></footer>;
}
export function Modal({ title, children, onClose, busy = false }: { title: string; children: ReactNode; onClose: () => void; busy?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  useEffect(() => {
    const dialog = ref.current;
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previous = document.body.style.overflow;
    dialog?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = previous;
      // React may remove the focused dialog before the browser restores focus.
      queueMicrotask(() => { if (trigger?.isConnected) trigger.focus(); });
    };
  }, []);
  return <dialog ref={ref} className="form-dialog" aria-labelledby={id} onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header><h2 id={id}>{title}</h2><button type="button" className="icon-button" aria-label="Cerrar formulario" disabled={busy} onClick={onClose}><X size={20} /></button></header>
    {children}
  </dialog>;
}
