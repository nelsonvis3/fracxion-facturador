import { artifactPath, expect, test } from "./fixtures";
import { api, mutate, register } from "./support";
import { checkAccessibility } from "./accessibility";

test("indicadores reales, filtros de moneda y reversiones cambian los resultados", async ({ page }) => {
  const tenant = await register(page); const base = `/api/tenants/${tenant.id}`;
  await page.emulateMedia({ reducedMotion: "reduce" });
  const customer = await mutate(page.request, `${base}/customers/`, { name: "Cliente de análisis" }); expect(customer.status()).toBe(201);
  const product = await mutate(page.request, `${base}/products/`, { name: "Servicio analítico", unit_price: "100.00", tax_rate: "21.00", currency: "ARS", product_type: "service", unit: "unit" }); expect(product.status()).toBe(201);
  const draft = await mutate(page.request, `${base}/invoices/`, { customer: (await customer.json()).id, currency: "ARS", due_date: "2020-01-01", lines: [{ product: (await product.json()).id, quantity: "2" }] }); expect(draft.status()).toBe(201);
  const invoice = await draft.json(); expect((await mutate(page.request, `${base}/invoices/${invoice.id}/issue/`, {})).status()).toBe(200);
  const payload = { invoice: invoice.id, amount: "40.00", method: "cash" };
  const payment = await mutate(page.request, `${base}/payments/`, payload, "POST", { "Idempotency-Key": "analytics-live-request" }); expect(payment.status()).toBe(201);
  const retry = await mutate(page.request, `${base}/payments/`, payload, "POST", { "Idempotency-Key": "analytics-live-request" }); expect(retry.status()).toBe(201);
  expect((await retry.json()).id).toBe((await payment.json()).id);
  await page.goto(`/dashboard/${tenant.id}/analytics`);
  const metrics = page.getByRole("region", { name: "Indicadores financieros" });
  await expect(metrics.getByText("ARS 242,00", { exact: true })).toBeVisible();
  await expect(metrics.getByText("ARS 40,00", { exact: true })).toBeVisible();
  await expect(metrics.getByText("ARS 202,00", { exact: true })).toHaveCount(2);
  await page.getByLabel("Moneda ISO", { exact: true }).fill("USD");
  await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
  await expect(metrics.getByText("USD 0,00", { exact: true })).toHaveCount(4);
  await page.getByLabel("Moneda ISO", { exact: true }).fill("ARS");
  await page.getByRole("button", { name: "Aplicar filtros", exact: true }).click();
  await expect(metrics.getByText("ARS 40,00", { exact: true })).toBeVisible();
  const paid = await payment.json(); expect((await mutate(page.request, `${base}/payments/${paid.id}/reverse/`, { reason: "Corrección E2E" })).status()).toBe(201);
  await page.getByRole("button", { name: "Actualizar datos", exact: true }).click();
  await expect(metrics.getByText("ARS 0,00", { exact: true })).toBeVisible();
  await expect(metrics.getByText("ARS 242,00", { exact: true })).toHaveCount(3);
  await page.screenshot({ path: artifactPath("analytics-desktop.png"), fullPage: true });
});

test("módulos empresariales son accesibles y no desbordan en escritorio y móvil", async ({ page }) => {
  test.setTimeout(90000);
  const tenant = await register(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect((await mutate(page.request, `/api/tenants/${tenant.id}/customers/`, { name: "Cliente accesible", email: "accessible@example.com" })).status()).toBe(201);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    for (const route of ["customers", "products", "settings", "team", "analytics"]) {
      await page.goto(`/dashboard/${tenant.id}/${route}`);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await checkAccessibility(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (["settings", "team", "analytics"].includes(route)) await page.screenshot({ path: artifactPath(`${route}-${width}.png`), fullPage: true });
    }
  }
  const identity = await page.request.get(`${api}/api/auth/me/`); expect(identity.status()).toBe(200);
});
