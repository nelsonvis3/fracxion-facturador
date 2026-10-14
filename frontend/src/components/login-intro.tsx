"use client";

import { useEffect, useRef, type ReactNode } from "react";
import type { HyperframesPlayer } from "@hyperframes/player";

import { BrandMark } from "./brand-mark";

// Client-side navigation keeps this module alive; a full refresh creates a new
// document and resets it. No browser storage or user data is needed.
let introducedInDocument = false;

export function LoginIntro({ children }: { children: ReactNode }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const finishRef = useRef<() => void>(() => {});

  useEffect(() => {
    const root = rootRef.current;
    const content = contentRef.current;
    const overlay = overlayRef.current;
    const host = hostRef.current;
    if (!root || !content || !overlay || !host) return;

    let disposed = false;
    let finished = false;
    let player: HyperframesPlayer | undefined;
    const controller = new AbortController();
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");

    function finish() {
      if (disposed || finished) return;
      finished = true;
      introducedInDocument = true;
      clearTimeout(timeout);
      controller.abort();
      player?.pause();
      const restoreFocus = overlay!.contains(document.activeElement);
      overlay!.hidden = true;
      content!.inert = false;
      content!.removeAttribute("aria-hidden");
      root!.dataset.introState = "complete";
      if (restoreFocus) content!.querySelector<HTMLInputElement>("#email")?.focus({ preventScroll: true });
      player?.remove();
    }
    const timeout = setTimeout(finish, 9000);
    finishRef.current = finish;

    // Consume the marker left by older builds, but also play the introduction
    // after logout. A full reload has already discarded all private views.
    const afterLogout = window.location.hash === "#salida";
    if (afterLogout) window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
    if (motion.matches || introducedInDocument) {
      finish();
      return () => { disposed = true; };
    }

    // Keep the real login mounted, but exclude it from keyboard and screen reader
    // navigation until the visual introduction has finished or been skipped.
    content.inert = true;
    content.setAttribute("aria-hidden", "true");
    overlay.hidden = false;
    root.dataset.introState = "loading";

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") finish();
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", finish);
    motion.addEventListener("change", finish);

    async function start() {
      try {
        const [{ HyperframesPlayer: Player }, response] = await Promise.all([
          import("@hyperframes/player"),
          fetch("/hyperframes/fracxion-intro/index.html", { signal: controller.signal }),
        ]);
        if (!response.ok) throw new Error("The introduction could not be loaded.");
        const html = await response.text();
        if (disposed || finished) return;

        // srcdoc embeds trusted, local content and preserves the site's DENY
        // frame header. No other page or external composition is embedded.
        const source = new DOMParser().parseFromString(html, "text/html");
        const stage = source.querySelector<HTMLElement>("[data-composition-id]");
        const target = [...content!.querySelectorAll<HTMLElement>("[data-login-brand]")]
          .find(element => element.getBoundingClientRect().width > 0);
        if (!stage || !target) throw new Error("Missing introduction layout.");
        const destination = target.getBoundingClientRect();
        stage.dataset.width = String(window.innerWidth);
        stage.dataset.height = String(window.innerHeight);
        stage.dataset.targetX = String(destination.left);
        stage.dataset.targetY = String(destination.top);
        stage.dataset.targetSize = String(destination.width);
        const runtimeUrl = new URL("/hyperframes/vendor/hyperframes-runtime.js", window.location.origin).href;
        const runtimeScript = source.querySelector<HTMLScriptElement>('script[src="/hyperframes/vendor/hyperframes-runtime.js"]');
        if (!runtimeScript) throw new Error("Missing local animation runtime.");
        runtimeScript.src = runtimeUrl;

        player = new Player();
        player.setAttribute("width", String(window.innerWidth));
        player.setAttribute("height", String(window.innerHeight));
        player.setAttribute("muted", "");
        player.setAttribute("disable-click-to-play", "");
        player.setAttribute("assets-loading-ui", "none");
        player.setAttribute("runtime-src", runtimeUrl);
        player.style.background = "transparent";
        player.addEventListener("ready", () => {
          if (disposed || finished || !player) return;
          player.iframeElement.title = "Animación de la marca Fracxion";
          player.iframeElement.tabIndex = -1;
          root!.dataset.introState = "playing";
          player.play();
        });
        player.addEventListener("ended", finish);
        player.addEventListener("error", finish);
        player.addEventListener("playbackerror", finish);
        player.setAttribute("srcdoc", "<!doctype html>" + source.documentElement.outerHTML);
        host!.appendChild(player);
      } catch {
        finish();
      }
    }
    void start();

    return () => {
      disposed = true;
      clearTimeout(timeout);
      controller.abort();
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", finish);
      motion.removeEventListener("change", finish);
      player?.pause();
      player?.remove();
      content.inert = false;
      content.removeAttribute("aria-hidden");
      // React Activity can keep an inactive route in the DOM. Release the CSS
      // scroll lock when its effects are suspended, as well as on completion.
      root.dataset.introState = "complete";
    };
  }, []);

  return (
    <div ref={rootRef} className="login-experience" data-intro-state="pending">
      <div ref={contentRef} className="login-content">{children}</div>
      <div ref={overlayRef} className="login-intro">
        <div className="login-intro-fallback" aria-hidden="true">
          <span className="login-intro-mark"><BrandMark /></span>
        </div>
        <div ref={hostRef} className="login-intro-player" aria-hidden="true" />
        <button type="button" className="login-intro-skip" onClick={() => finishRef.current()}>
          Omitir introducción <span aria-hidden="true">↗</span>
        </button>
      </div>
      <noscript><style>{".login-intro { display: none !important; } html:has(.login-experience), body:has(.login-experience) { overflow: visible !important; }"}</style></noscript>
    </div>
  );
}
