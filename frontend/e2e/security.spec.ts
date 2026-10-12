import type { APIRequestContext } from "@playwright/test";
import { test, expect } from "./fixtures";

const api = "http://127.0.0.1:8001";
const tenant = "00000000-0000-4000-8000-000000000001";
const root = `/api/tenants/${tenant}`;
const password = "SyntheticE2EPassword2026!";

async function token(request: APIRequestContext) {
  const response = await request.get(`${api}/api/auth/csrf/`);
  expect(response.status()).toBe(200);
  return (await response.json()).csrfToken as string;
}

async function post(request: APIRequestContext, path: string, data: unknown) {
  return request.post(`${api}${path}`, {
    data: JSON.stringify(data),
    headers: { "Content-Type": "application/json", "X-CSRFToken": await token(request) },
  });
}

async function login(request: APIRequestContext, role = "owner") {
  const response = await post(request, "/api/auth/login/", { email: `${role}@e2e.example`, password });
  expect(response.status()).toBe(200);
  expect(Object.keys((await response.json()).user).sort()).toEqual(["email", "first_name", "id", "last_name"]);
}

test("API exige CSRF, rechaza origen ajeno y evita caché de identidad", async ({ request }) => {
  const me = await request.get(`${api}/api/auth/me/`);
  expect(me.status()).toBe(401);
  expect(me.headers()["cache-control"]).toBe("private, no-store");
  const csrf = await token(request);
  const noToken = await request.post(`${api}/api/auth/login/`, { data: { email: "owner@e2e.example", password } });
  expect(noToken.status()).toBe(403);
  const foreignOrigin = await request.post(`${api}/api/auth/login/`, {
    data: { email: "owner@e2e.example", password },
    headers: { "X-CSRFToken": csrf, Origin: "http://untrusted.example" },
  });
  expect(foreignOrigin.status()).toBe(403);
  const cors = await request.get(`${api}/api/auth/csrf/`, { headers: { Origin: "http://untrusted.example" } });
  expect(cors.headers()["access-control-allow-origin"]).toBeUndefined();
});

test("viewer no puede escribir enviando privilegios falsificados", async ({ request }) => {
  await login(request, "viewer");
  expect((await request.get(`${api}${root}/customers/`)).status()).toBe(200);
  for (const resource of ["customers", "products", "invoices", "payments"]) {
    const response = await post(request, `${root}/${resource}/`, { role: "owner", is_superuser: true, name: "Intento rechazado" });
    expect(response.status(), resource).toBe(403);
  }
  expect((await request.get(`${api}${root}/audit-events/`)).status()).toBe(403);
});

test("datos de otra empresa no se leen ni se usan como relaciones", async ({ request, playwright }) => {
  await login(request);
  const other = await playwright.request.newContext();
  try {
    const registration = await post(other, "/api/auth/register/", {
      first_name: "Aislamiento",
      company_name: "Empresa ajena sintética",
      email: `isolation.${Date.now()}@e2e.example`,
      password,
      password_confirm: password,
    });
    expect(registration.status()).toBe(201);
    const otherTenant = (await registration.json()).tenant.id as string;
    const otherRoot = `/api/tenants/${otherTenant}`;
    const customerResponse = await post(other, `${otherRoot}/customers/`, { name: "Cliente privado sintético" });
    expect(customerResponse.status()).toBe(201);
    const customer = (await customerResponse.json()).id as string;
    const productResponse = await post(other, `${otherRoot}/products/`, {
      name: "Producto privado sintético", unit_price: "100.00", tax_rate: "21.00", currency: "ARS",
    });
    expect(productResponse.status()).toBe(201);
    const product = (await productResponse.json()).id as string;
    const ownCustomerResponse = await post(request, `${root}/customers/`, { name: `Cliente aislamiento ${Date.now()}` });
    expect(ownCustomerResponse.status()).toBe(201);
    const ownCustomer = (await ownCustomerResponse.json()).id as string;

    for (const resource of ["customers", "products", "invoices", "payments", "audit-events"]) {
      const denied = await request.get(`${api}${otherRoot}/${resource}/`);
      expect(denied.status(), resource).toBe(403);
      expect(JSON.stringify(await denied.json())).not.toContain("privado sintético");
    }
    expect((await request.get(`${api}${root}/customers/${customer}/`)).status()).toBe(404);
    expect((await request.get(`${api}${root}/products/${product}/`)).status()).toBe(404);
    const deniedCustomer = await post(request, `${root}/invoices/`, {
      customer, currency: "ARS", lines: [{ product, quantity: "1" }],
    });
    expect(deniedCustomer.status()).toBe(400);
    const deniedProduct = await post(request, `${root}/invoices/`, {
      customer: ownCustomer, currency: "ARS", lines: [{ product, quantity: "1" }],
    });
    expect(deniedProduct.status()).toBe(400);
  } finally {
    await other.dispose();
  }
});

test("entradas malformadas reciben 400 en la API en ejecución", async ({ request }) => {
  for (const body of ['{"email":' + "9".repeat(5000) + "}", JSON.stringify({ email: "bad\ud800@example.com" }), JSON.stringify({ email: "bad\x00@example.com" })]) {
    const response = await request.post(`${api}/api/auth/password-reset/`, {
      data: body,
      headers: { "Content-Type": "application/json", "X-CSRFToken": await token(request) },
    });
    expect(response.status()).toBe(400);
    expect(response.headers()["cache-control"]).toBe("private, no-store");
  }
});

test("logout descarta datos privados ocultos y evita recuperarlos desde el historial", async ({ page }) => {
  const customerName = `AA Cliente privacidad ${Date.now()}`;
  async function signIn() {
    await page.goto("/");
    await page.locator(".login-form").getByLabel("Correo electrónico", { exact: true }).fill("owner@e2e.example");
    await page.locator(".login-form").getByLabel("Contraseña", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
  }
  async function assertCleared() {
    await expect(page).toHaveURL("http://127.0.0.1:3010/");
    await expect(page.getByRole("button", { name: "Iniciar sesión", exact: true })).toBeVisible();
    const body = await page.locator("body").textContent();
    expect(body).not.toContain(customerName);
    expect(body).not.toContain("Empresa E2E");
    expect((await page.request.get(`${api}/api/auth/me/`)).status()).toBe(401);
  }
  await signIn();
  expect((await post(page.request, `${root}/customers/`, { name: customerName })).status()).toBe(201);
  await page.goto(`/dashboard/${tenant}/customers`);
  await expect(page.getByText(customerName, { exact: true })).toBeVisible();
  await page.getByRole("navigation", { name: "Módulos de empresa" }).getByRole("link", { name: "Productos y servicios", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Productos y servicios", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cerrar sesión", exact: true }).click();
  await assertCleared();
  await page.goBack();
  await assertCleared();

  await signIn();
  await page.goto(`/dashboard/${tenant}/customers`);
  await expect(page.getByText(customerName, { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Cambiar empresa", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.getByRole("button", { name: "Cerrar sesión", exact: true }).click();
  await assertCleared();
});
