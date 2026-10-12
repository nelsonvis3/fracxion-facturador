"use client";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Alert, useAsync } from "./business-ui";
import type { Page } from "@/lib/business-api";

export function ResourceSelect<T extends { id: string }>({ label, selected, onSelect, loader, describe, emptyMessage = "No hay opciones disponibles." }: { label: string; selected: T | null; onSelect: (item: T | null) => void; loader: (search: string, page: number) => Promise<Page<T>>; describe: (item: T) => string; emptyMessage?: ReactNode }) {
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => { const timer = setTimeout(() => { setDebounced(search); setPage(1); }, 300); return () => clearTimeout(timer); }, [search]);
  const state = useAsync(useCallback(() => loader(debounced, page), [loader, debounced, page]));
  const options = [...(selected ? [selected] : []), ...(state.data?.results ?? []).filter(item => item.id !== selected?.id)];
  const empty = !state.loading && !state.error && state.data?.results.length === 0 && search === debounced;
  return <div className="field"><label>{label}<select className="input mt-2" required aria-label={label} value={selected?.id ?? ""} disabled={state.loading || !!state.error || (empty && !selected)} onChange={event => onSelect(options.find(item => item.id === event.target.value) ?? null)}><option value="">{state.loading ? "Cargando opciones…" : empty && !selected ? "No hay opciones disponibles" : "Seleccioná una opción"}</option>{options.map(item => <option key={item.id} value={item.id}>{describe(item)}</option>)}</select></label>
    <input className="input" aria-label={`Buscar ${label.toLowerCase()}`} placeholder={`Buscar ${label.toLowerCase()}…`} value={search} onChange={event => setSearch(event.target.value)} />
    {empty && <div className="notice-info" role="status">{debounced.trim() ? "No hay resultados para esa búsqueda. Probá con otros datos o borrá la búsqueda." : emptyMessage}</div>}
    {state.error && <Alert>{state.error}<button type="button" className="button secondary" onClick={state.refresh}>Reintentar</button></Alert>}
    {state.data && (state.data.previous || state.data.next) && <div className="row-actions"><button type="button" className="button secondary" disabled={state.loading || !state.data.previous} onClick={() => setPage(value => value - 1)}>Anteriores</button><button type="button" className="button secondary" disabled={state.loading || !state.data.next} onClick={() => setPage(value => value + 1)}>Más opciones</button></div>}
  </div>;
}
