import type { Page, APIRequestContext } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { expect } from "@playwright/test";

export const api = "http://127.0.0.1:8001";
export async function mutate(request: APIRequestContext, path: string, data: object, method = "POST", headers: Record<string, string> = {}) {
  const csrf = (await (await request.get(`${api}/api/auth/csrf/`)).json()).csrfToken;
  return request.fetch(`${api}${path}`, { method, headers: { "X-CSRFToken": csrf, Origin: "http://127.0.0.1:3010", ...headers }, data });
}
export async function register(page: Page) {
  const id = randomUUID();
  return signUp(page.request, { first_name: "Enterprise", company_name: `Empresa ${id}`, email: `enterprise.${id}@e2e.example`, password: "SyntheticEnterprisePassword2026!", password_confirm: "SyntheticEnterprisePassword2026!" });
}
/** Registers through the API and confirms the emailed code, like a real new owner. */
export async function signUp(request: APIRequestContext, data: { email: string } & Record<string, string>) {
  const response = await mutate(request, "/api/auth/register/", data);
  expect(response.status()).toBe(201);
  const confirmed = await mutate(request, "/api/auth/signup-code/confirm/", { email: data.email, code: signupCode(data.email) });
  expect(confirmed.status()).toBe(200);
  return (await (await request.get(`${api}/api/auth/tenants/`)).json()).results[0] as { id: string; name: string };
}
/** Reads a fresh code straight from the synthetic database; the API never exposes it. */
export function signupCode(email: string) {
  return execFileSync(process.env.E2E_PYTHON ?? resolve("../backend/.venv/bin/python"), ["scripts/signup_code_e2e.py", email], { cwd: resolve("../backend"), env: { ...process.env, DJANGO_SETTINGS_MODULE: "config.e2e_settings" }, encoding: "utf8" }).trim();
}
