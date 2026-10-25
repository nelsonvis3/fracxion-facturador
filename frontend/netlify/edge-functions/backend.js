/* global Netlify */

const requestHeaders = [
  "accept", "accept-language", "content-type", "cookie", "origin", "referer",
  "x-csrftoken", "idempotency-key", "range", "if-none-match", "if-modified-since",
];

function unavailable() {
  return Response.json(
    { detail: "El servicio está iniciando o no está disponible. Esperá un minuto y volvé a intentar." },
    { status: 503, headers: { "Cache-Control": "private, no-store", "Retry-After": "60" } },
  );
}

export default async function backend(request, context) {
  const secret = Netlify.env.get("FRACXION_PROXY_SECRET");
  const configuredOrigin = Netlify.env.get("BACKEND_ORIGIN");
  if (!secret || secret.length < 32 || !configuredOrigin || !context.ip) return unavailable();

  let origin;
  try {
    origin = new URL(configuredOrigin);
    if (origin.protocol !== "https:" || origin.username || origin.password ||
        origin.pathname !== "/" || origin.search || origin.hash) return unavailable();
  } catch {
    return unavailable();
  }

  const incoming = new URL(request.url);
  if (incoming.protocol !== "https:") {
    incoming.protocol = "https:";
    return Response.redirect(incoming, 308);
  }
  const target = new URL(origin);
  target.pathname = incoming.pathname;
  target.search = incoming.search;
  const headers = new Headers();
  for (const key of requestHeaders) {
    if (request.headers.has(key)) headers.set(key, request.headers.get(key));
  }
  // Values supplied by a visitor never reach Django as trusted proxy metadata.
  headers.set("X-Fracxion-Proxy-Secret", secret);
  headers.set("X-Fracxion-Client-IP", context.ip);
  headers.set("Accept-Encoding", "identity");

  try {
    const init = {
      method: request.method,
      headers,
      redirect: "manual",
      signal: AbortSignal.timeout(35_000),
    };
    if (!["GET", "HEAD"].includes(request.method)) init.body = request.body;
    const upstream = await fetch(target, init);
    if (incoming.pathname.startsWith("/api/") &&
        upstream.headers.get("content-type")?.includes("text/html")) {
      await upstream.body?.cancel();
      return unavailable();
    }
    const responseHeaders = new Headers(upstream.headers);
    responseHeaders.set("Cache-Control", "private, no-store");
    responseHeaders.delete("CDN-Cache-Control");
    responseHeaders.delete("Netlify-CDN-Cache-Control");
    // Django admin may redirect to its own origin. Keep navigation same-origin.
    const location = responseHeaders.get("Location");
    if (location) {
      const destination = new URL(location, target);
      if (destination.origin === origin.origin) {
        destination.host = incoming.host;
        destination.protocol = incoming.protocol;
        responseHeaders.set("Location", destination.href);
      }
    }
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
    // Never retry mutations: a lost response does not mean the write failed.
    return unavailable();
  }
}
