import type { APIRequestContext } from "@playwright/test";
import { artifactPath, expect, test } from "./fixtures";

const api = "http://127.0.0.1:8001";

async function post(request: APIRequestContext, path: string, data: unknown) {
  const csrfResponse = await request.get(`${api}/api/auth/csrf/`);
  expect(csrfResponse.status()).toBe(200);
  const { csrfToken } = await csrfResponse.json();
  return request.post(`${api}${path}`, {
    data: JSON.stringify(data),
    headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
  });
}

test("Pagos explica el selector vacío y permite elegir una factura emitida y registrar el cobro", async ({ page }) => {
  test.setTimeout(60000);
  const suffix = Date.now();
  const password = "SyntheticPaymentPassword2026!";
  const registration = await post(page.request, "/api/auth/register/", {
    first_name: "Prueba",
    company_name: `Empresa pagos ${suffix}`, email: `payments.${suffix}@e2e.example`,
    password, password_confirm: password,
  });
  expect(registration.status()).toBe(201);
  const tenant = (await registration.json()).tenant.id as string;
  const base = `/dashboard/${tenant}`;
  const root = `/api/tenants/${tenant}`;
  await page.goto(`${base}/payments`);
  await page.getByRole("button", { name: "Registrar pago", exact: true }).click();
  let form = page.getByRole("dialog", { name: "Registrar pago", exact: true });
  await expect(form.getByRole("status")).toContainText("No hay facturas emitidas en esta empresa");
  await expect(form.getByLabel("Factura emitida", { exact: true })).toBeDisabled();
  await expect(form.getByRole("button", { name: "Registrar pago", exact: true })).toBeDisabled();
  await form.getByRole("link", { name: "Ver facturas", exact: true }).click();
  await expect(page).toHaveURL(`${base}/invoices`);
  await expect(page.getByRole("dialog")).toHaveCount(0);

  const customerResponse = await post(page.request, `${root}/customers/`, { name: `Cliente pagos ${suffix}` });
  expect(customerResponse.status()).toBe(201);
  const customer = (await customerResponse.json()).id as string;
  const productResponse = await post(page.request, `${root}/products/`, { name: "Servicio de prueba", unit_price: "100.00", tax_rate: "21.00", currency: "ARS" });
  expect(productResponse.status()).toBe(201);
  const product = (await productResponse.json()).id as string;
  const draftResponse = await post(page.request, `${root}/invoices/`, { customer, currency: "ARS", lines: [{ product, quantity: "1" }] });
  expect(draftResponse.status()).toBe(201);
  const draft = await draftResponse.json();

  // Un borrador existente tampoco debe aparecer como opción de cobro.
  await page.goto(`${base}/payments`);
  await page.getByRole("button", { name: "Registrar pago", exact: true }).click();
  form = page.getByRole("dialog", { name: "Registrar pago", exact: true });
  await expect(form.getByRole("status")).toContainText("No hay facturas emitidas en esta empresa");
  await expect(form.getByLabel("Factura emitida", { exact: true }).locator(`option[value="${draft.id}"]`)).toHaveCount(0);
  await form.getByRole("button", { name: "Cancelar", exact: true }).click();

  await page.goto(`${base}/invoices/${draft.id}`);
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Emitir factura interna", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Interna #/ })).toBeVisible();
  await page.goto(`${base}/payments`);
  await page.getByRole("button", { name: "Registrar pago", exact: true }).click();
  form = page.getByRole("dialog", { name: "Registrar pago", exact: true });
  const invoices = form.getByLabel("Factura emitida", { exact: true });
  await expect(invoices).toBeEnabled();
  await expect(invoices.locator(`option[value="${draft.id}"]`)).toContainText(`Cliente pagos ${suffix} · Saldo ARS 121,00`);

  await form.getByLabel("Buscar factura emitida", { exact: true }).fill("Sin coincidencias de prueba");
  await expect(form.getByRole("status")).toContainText("No hay resultados para esa búsqueda");
  await expect(form.getByText("No hay facturas emitidas en esta empresa", { exact: false })).toHaveCount(0);
  await form.getByLabel("Buscar factura emitida", { exact: true }).fill(`Cliente pagos ${suffix}`);
  await expect(invoices.locator(`option[value="${draft.id}"]`)).toBeAttached();
  await invoices.selectOption(draft.id);
  await form.getByLabel("Importe (ARS) *", { exact: true }).fill("40.00");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: artifactPath("payment-selector.png"), fullPage: true });
  await form.getByRole("button", { name: "Registrar pago", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("cell", { name: "ARS 40,00", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("cell", { name: "ARS 40,00", exact: true })).toBeVisible();
  const saved = await page.request.get(`${api}${root}/invoices/${draft.id}/`);
  expect(saved.status()).toBe(200);
  expect((await saved.json()).balance).toBe("81.00");
});
