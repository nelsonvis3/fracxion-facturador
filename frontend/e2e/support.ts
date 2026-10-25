import type { Page, APIRequestContext } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { expect } from "@playwright/test";

export const api = "http://127.0.0.1:8001";
export async function mutate(request: APIRequestContext, path: string, data: object, method = "POST", headers: Record<string, string> = {}) {
  const csrf = (await (await request.get(`${api}/api/auth/csrf/`)).json()).csrfToken;
  return request.fetch(`${api}${path}`, { method, headers: { "X-CSRFToken": csrf, Origin: "http://127.0.0.1:3010", ...headers }, data });
}
export async function register(page: Page) {
  const id = randomUUID();
  const response = await mutate(page.request, "/api/auth/register/", { first_name: "Enterprise", company_name: `Empresa ${id}`, email: `enterprise.${id}@e2e.example`, password: "SyntheticEnterprisePassword2026!", password_confirm: "SyntheticEnterprisePassword2026!" });
  expect(response.status()).toBe(201); return (await response.json()).tenant as { id: string; name: string };
}
