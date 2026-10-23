import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import backend from "../frontend/netlify/edge-functions/backend.js";

const originalFetch = globalThis.fetch;
const secret = "synthetic-shared-secret-at-least-32-characters";
globalThis.Netlify = { env: { get: (key) => ({ BACKEND_ORIGIN: "https://api.example", FRACXION_PROXY_SECRET: secret })[key] } };
afterEach(() => { globalThis.fetch = originalFetch; });

test("proxy preserves cookies, CSRF and body while replacing forged proxy headers", async () => {
  globalThis.fetch = async (url, init) => {
    assert.equal(url.href, "https://api.example/api/auth/login/?next=home");
    assert.equal(init.headers.get("x-fracxion-proxy-secret"), secret);
    assert.equal(init.headers.get("x-fracxion-client-ip"), "203.0.113.5");
    assert.equal(init.headers.get("cookie"), "sessionid=opaque");
    assert.equal(init.headers.get("x-csrftoken"), "csrf");
    assert.equal(init.headers.get("origin"), "https://site.example");
    assert.equal(init.headers.get("x-forwarded-for"), null);
    assert.equal(init.headers.get("host"), null);
    assert.equal(init.redirect, "manual");
    assert.equal(await new Response(init.body).text(), '{"email":"test@example.com"}');
    const headers = new Headers({ "Content-Type": "application/json" });
    headers.append("Set-Cookie", "sessionid=new; Secure; HttpOnly; SameSite=Lax; Path=/");
    headers.append("Set-Cookie", "csrftoken=new; Secure; HttpOnly; SameSite=Lax; Path=/");
    return new Response("{}", { headers });
  };
  const response = await backend(new Request("https://site.example/api/auth/login/?next=home", {
    method: "POST", body: '{"email":"test@example.com"}', headers: {
      Cookie: "sessionid=opaque", "X-CSRFToken": "csrf", Origin: "https://site.example",
      "X-Fracxion-Proxy-Secret": "forged", "X-Fracxion-Client-IP": "forged",
      "X-Forwarded-For": "forged", Host: "forged.example",
    },
  }), { ip: "203.0.113.5" });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "private, no-store");
  assert.equal(response.headers.getSetCookie().length, 2);
});

test("backend redirects remain on frontend and are never followed with secrets", async () => {
  globalThis.fetch = async () => new Response(null, { status: 302, headers: { Location: "https://api.example/admin/login/" } });
  const response = await backend(new Request("https://site.example/admin/"), { ip: "203.0.113.5" });
  assert.equal(response.headers.get("location"), "https://site.example/admin/login/");
});

test("network failures return a retryable error without replaying a mutation", async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls++; throw new Error("sensitive upstream details"); };
  const response = await backend(new Request("https://site.example/api/invoices/", { method: "POST", body: "{}" }), { ip: "203.0.113.5" });
  assert.equal(calls, 1);
  assert.equal(response.status, 503);
  assert.equal(response.headers.get("retry-after"), "60");
  assert.ok(!(await response.text()).includes("sensitive"));
});

test("missing platform client IP never reaches backend", async () => {
  globalThis.fetch = async () => { assert.fail("must not forward"); };
  assert.equal((await backend(new Request("https://site.example/api/auth/csrf/"), {})).status, 503);
});

test("Render cold-start HTML becomes a retryable API response", async () => {
  globalThis.fetch = async () => new Response("<html>Starting</html>", { headers: { "Content-Type": "text/html" } });
  const response = await backend(new Request("https://site.example/api/auth/csrf/"), { ip: "203.0.113.5" });
  assert.equal(response.status, 503);
  assert.match(response.headers.get("content-type"), /application\/json/);
});
