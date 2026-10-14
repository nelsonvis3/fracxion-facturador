"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { gsap } from "gsap";
import { BrandMark } from "./brand-mark";

type TransitionKind = "welcome" | "farewell";
type Presentation = { kind: TransitionKind; name: string };
type Phase = "greeting" | "loading" | "revealing";
type Presenter = (kind: TransitionKind, name: string) => Promise<void>;
const TransitionContext = createContext<{ present: Presenter; destinationReady: () => void } | null>(null);

export function useSessionTransition() {
  const context = useContext(TransitionContext);
  if (!context) throw new Error("Se requiere el contexto de transición de sesión.");
  return context.present;
}

// The destination reports its real data state, rather than guessing a route's
// readiness from a navigation event or an arbitrary delay.
export function useSessionTransitionReady(ready: boolean) {
  const context = useContext(TransitionContext);
  if (!context) throw new Error("Se requiere el contexto de transición de sesión.");
  const { destinationReady } = context;
  useEffect(() => { if (ready) destinationReady(); }, [ready, destinationReady]);
}

export function SessionTransitionProvider({ children }: { children: ReactNode }) {
  const [presentation, setPresentation] = useState<Presentation | null>(null);
  const [phase, setPhase] = useState<Phase>("greeting");
  const pendingRef = useRef<{ kind: TransitionKind; promise: Promise<void>; resolve: () => void } | null>(null);
  const advanceRef = useRef<() => void>(() => {});
  const contentRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);

  const finish = useCallback(() => {
    const pending = pendingRef.current;
    if (!pending) return;
    pendingRef.current = null;
    // Keep the F and background while the caller navigates. Farewell keeps
    // private views unmounted until the mandatory full reload, as before.
    setPhase("loading");
    pending.resolve();
  }, []);

  const destinationReady = useCallback(() => {
    if (window.location.pathname.startsWith("/dashboard")) {
      setPhase(current => current === "loading" ? "revealing" : current);
    }
  }, []);

  const present = useCallback<Presenter>((kind, name) => {
    if (pendingRef.current) return pendingRef.current.promise;
    if (kind === "welcome" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return Promise.resolve();
    let resolve!: () => void;
    const promise = new Promise<void>(done => { resolve = done; });
    pendingRef.current = { kind, promise, resolve };
    setPhase("greeting");
    setPresentation({ kind, name: name.trim().slice(0, 160) || "tu espacio de trabajo" });
    return promise;
  }, []);

  useEffect(() => {
    if (!presentation) return;
    const overlay = overlayRef.current;
    const content = contentRef.current;
    if (!overlay) { finish(); return; }
    let disposed = false;
    let context: gsap.Context | undefined;
    advanceRef.current = finish;
    const previousFocus = document.activeElement;
    if (content) { content.inert = true; content.setAttribute("aria-hidden", "true"); }
    overlay.focus({ preventScroll: true });
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const timeout = setTimeout(() => advanceRef.current(), 5000);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") advanceRef.current();
      if (event.key === "Tab") {
        event.preventDefault();
        const button = overlay!.querySelector<HTMLButtonElement>("button:not(:disabled)");
        (button || overlay!).focus();
      }
    };
    window.addEventListener("keydown", onKey);
    const onMotionChange = () => advanceRef.current();
    motion.addEventListener("change", onMotionChange);

    async function animate() {
      if (motion.matches) { overlay!.dataset.motion = "static"; finish(); return; }
      try {
        const { gsap } = await import("gsap");
        if (disposed || !pendingRef.current) return;
        context = gsap.context(() => {
          const mark = overlay!.querySelector<HTMLElement>(".session-transition-mark")!;
          const origin = mark.getBoundingClientRect();
          const size = Math.min(112, innerWidth * .2);
          const timeline = gsap.timeline({ onComplete: finish });
          advanceRef.current = () => { if (pendingRef.current) timeline.progress(1); };
          timeline.fromTo(".session-transition-mark", { y: 12, scale: .92, opacity: 0 }, { y: 0, scale: 1, opacity: 1, duration: .45, ease: "power3.out" }, 0);
          timeline.fromTo(".session-transition-heading, .session-transition-note", { y: 18, opacity: 0 }, { y: 0, opacity: 1, duration: .55, stagger: .1, ease: "power3.out" }, .12);
          timeline.to(".session-transition-heading, .session-transition-note", { y: -8, opacity: 0, duration: .35, ease: "power2.inOut" }, 1.35);
          timeline.to(mark, { x: innerWidth / 2 - (origin.left + origin.width / 2), y: innerHeight / 2 - (origin.top + origin.height / 2), scale: size / origin.width, duration: .75, ease: "power3.inOut" }, 1.35);
          // End on one complete turn so the next document starts with the same F.
          timeline.to(".session-transition-spin", { rotation: 360, duration: .75, ease: "power2.inOut" }, 1.35);
        }, overlay!);
      } catch {
        overlay!.dataset.motion = "static";
        finish();
      }
    }
    void animate();
    return () => {
      disposed = true;
      clearTimeout(timeout);
      window.removeEventListener("keydown", onKey);
      motion.removeEventListener("change", onMotionChange);
      context?.revert();
      advanceRef.current = () => {};
      if (content) { content.inert = false; content.removeAttribute("aria-hidden"); }
      if (presentation.kind === "welcome" && previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, [presentation, finish]);

  useEffect(() => {
    if (!presentation || presentation.kind !== "welcome" || phase === "greeting") return;
    // A broken route must not leave the app blocked behind its presentation.
    if (phase === "loading") {
      const timeout = setTimeout(() => setPhase("revealing"), 12000);
      return () => clearTimeout(timeout);
    }
    const overlay = overlayRef.current;
    if (!overlay) return;
    overlay.focus({ preventScroll: true });
    let disposed = false;
    let context: gsap.Context | undefined;
    async function reveal() {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setPresentation(null); return; }
      try {
        const { gsap } = await import("gsap");
        if (disposed) return;
        context = gsap.context(() => {
          gsap.to(overlay!, { opacity: 0, duration: .65, ease: "power2.inOut", onComplete: () => setPresentation(null) });
        }, overlay!);
      } catch { if (!disposed) setPresentation(null); }
    }
    void reveal();
    return () => { disposed = true; context?.revert(); };
  }, [phase, presentation]);

  useEffect(() => () => { pendingRef.current?.resolve(); pendingRef.current = null; }, []);

  return (
    <TransitionContext.Provider value={{ present, destinationReady }}>
      {presentation?.kind !== "farewell" && <div ref={contentRef} className="session-content">{children}</div>}
      {presentation && (
        <div ref={overlayRef} className="session-transition" data-session-transition={presentation.kind} data-phase={phase}
          role="dialog" aria-modal="true" aria-labelledby="session-transition-heading" tabIndex={-1}>
          <div className="session-transition-card">
            <span className="session-transition-mark" aria-hidden="true"><span className="session-transition-spin"><BrandMark /></span></span>
            <h1 id="session-transition-heading" className="session-transition-heading">
              {presentation.kind === "welcome" ? "Bienvenido/a," : "Hasta pronto,"}
              <span>{presentation.name}</span>
            </h1>
            <p className="session-transition-note">{presentation.kind === "welcome" ? "Tu espacio de trabajo está listo." : "Tu sesión se cerró correctamente."}</p>
          </div>
          <p className="session-transition-status" role="status">{phase !== "greeting" && presentation.kind === "welcome" ? "Cargando tu espacio de trabajo…" : ""}</p>
          <button className="login-intro-skip" type="button" disabled={phase !== "greeting"} onClick={() => advanceRef.current()}>Continuar <span aria-hidden="true">↗</span></button>
        </div>
      )}
    </TransitionContext.Provider>
  );
}
