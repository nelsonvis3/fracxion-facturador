import { readFileSync } from "node:fs";
import { artifactPath, expect, test } from "./fixtures";
import { api, mutate, register } from "./support";

test("configuración, logo, vencimiento y datos históricos persisten desde la interfaz", async ({ page }) => {
  test.setTimeout(60000);
  const tenant = await register(page); const base = `/dashboard/${tenant.id}`;
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`${base}/settings`);
  await page.getByLabel("Nombre visible *", { exact: true }).fill("Empresa de prueba histórica");
  await page.getByLabel("Zona horaria *", { exact: true }).fill("UTC");
  await page.getByLabel("Plazo predeterminado de pago (días)").fill("30");
  await page.getByLabel("Pie del comprobante", { exact: true }).fill("Condiciones históricas acordadas");
  await page.getByLabel("Subir logo PNG o JPEG", { exact: true }).setInputFiles({ name: "company.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFElEQVR4nGNkYPjPgA0wYRUdtBIAy0MBD1YkjLoAAAAASUVORK5CYII=", "base64") });
  await expect(page.getByRole("img", { name: "Logo de Empresa de prueba histórica", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Guardar configuración", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("quedó guardada");
  await page.reload(); await expect(page.getByLabel("Plazo predeterminado de pago (días)")).toHaveValue("30");
  expect((await page.request.get(`${api}/api/tenants/${tenant.id}/settings/logo/`)).status()).toBe(200);
  await page.screenshot({ path: artifactPath("settings-saved.png"), fullPage: true });
  const customer = await mutate(page.request, `/api/tenants/${tenant.id}/customers/`, { name: "Cliente de vencimientos" }); expect(customer.status()).toBe(201);
  const product = await mutate(page.request, `/api/tenants/${tenant.id}/products/`, { name: "Servicio de vencimientos", unit_price: "100.00", tax_rate: "21.00", currency: "ARS", product_type: "service", unit: "unit" }); expect(product.status()).toBe(201);
  await page.goto(`${base}/invoices/new`);
  await page.getByLabel("Cliente", { exact: true }).selectOption({ label: "Cliente de vencimientos" });
  await page.getByLabel("Producto", { exact: true }).selectOption({ label: "Servicio de vencimientos · ARS 100,00" });
  await page.getByLabel("Fecha de vencimiento", { exact: true }).fill("2020-01-01");
  await page.getByRole("button", { name: "Guardar borrador", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Borrador", exact: true })).toBeVisible();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Emitir factura interna", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Interna #/ })).toBeVisible();
  const invoiceUrl = page.url();
  await page.screenshot({ path: artifactPath("invoice-with-due-date.png"), fullPage: true });
  await expect(page.getByText("Condiciones históricas acordadas", { exact: true })).toBeVisible();
  await page.goto(`${base}/settings`);
  await page.getByLabel("Nombre visible *", { exact: true }).fill("Empresa renombrada");
  await page.getByLabel("Pie del comprobante", { exact: true }).fill("Nuevas condiciones");
  await page.getByRole("button", { name: "Guardar configuración", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("quedó guardada");
  await page.goto(invoiceUrl);
  await expect(page.getByText("Condiciones históricas acordadas", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Empresa de prueba histórica", exact: true })).toBeVisible();
  await page.goto(`${base}/invoices`);
  await page.getByLabel("Estado de cobro y vencimiento").selectOption("overdue");
  await expect(page.getByRole("row").filter({ hasText: "Cliente de vencimientos" })).toBeVisible();
  await page.getByLabel("Estado de cobro y vencimiento").selectOption("paid");
  await expect(page.getByText("No hay registros para los filtros seleccionados.", { exact: true })).toBeVisible();
});

test("equipo permite invitar, reenviar y revocar y protege al último propietario", async ({ page }) => {
  const tenant = await register(page); await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/dashboard/${tenant.id}/team`);
  const owner = page.getByRole("row").filter({ hasText: "Enterprise" }).last();
  page.once("dialog", dialog => dialog.accept()); await owner.getByRole("button", { name: "Desactivar", exact: true }).click();
  await expect(owner.getByRole("alert")).toContainText("al menos un propietario");
  const email = `invite.${Date.now()}@e2e.example`;
  await page.getByLabel("Correo del destinatario *", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Enviar invitación", exact: true }).click();
  const invitation = page.getByRole("row").filter({ hasText: email });
  await expect(invitation).toContainText("Pendiente");
  page.once("dialog", dialog => dialog.accept()); await invitation.getByRole("button", { name: "Reenviar", exact: true }).click();
  await expect(invitation.getByRole("button", { name: "Reenviar", exact: true })).toBeEnabled();
  page.once("dialog", dialog => dialog.accept()); await invitation.getByRole("button", { name: "Revocar", exact: true }).click();
  await expect(invitation).toContainText("Revocada");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("invitación real permite crear cuenta sin empresa extra y no admite reutilización", async ({ page }) => {
  const fixture = JSON.parse(readFileSync("e2e/invitation-fixture.json", "utf8")) as { token: string; email: string; tenant: string };
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/accept-invitation#token=${encodeURIComponent(fixture.token)}`);
  await expect(page.getByRole("heading", { name: "Unite a Empresa E2E", exact: true })).toBeVisible();
  await page.getByLabel("Nombre *", { exact: true }).fill("Invitado E2E");
  await page.getByLabel("Contraseña *", { exact: true }).fill("SyntheticInvitationPassword2026!");
  await page.getByLabel("Confirmá la contraseña *", { exact: true }).fill("SyntheticInvitationPassword2026!");
  await page.getByRole("button", { name: "Aceptar invitación", exact: true }).click();
  await expect(page).toHaveURL(`/dashboard/${fixture.tenant}`);
  await expect(page.locator(".business-company")).toContainText("Solo lectura");
  const companies = await (await page.request.get(`${api}/api/auth/tenants/`)).json();
  expect(companies.results).toHaveLength(1);
  await page.goto(`/accept-invitation#token=${encodeURIComponent(fixture.token)}`);
  await expect(page.getByRole("main").getByRole("alert")).toContainText("no es válida");
});

test("modal conserva navegación de teclado y devuelve el foco en sus tres cierres", async ({ page }) => {
  const tenant = await register(page); await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/dashboard/${tenant.id}/products`);
  const trigger = page.getByRole("button", { name: "Nuevo producto", exact: true });
  for (const close of ["Escape", "Cancelar", "Cerrar formulario"]) {
    await trigger.focus(); await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog"); await expect(dialog).toBeVisible();
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
    if (close === "Escape") await page.keyboard.press("Escape"); else await dialog.getByRole("button", { name: close, exact: true }).click();
    await expect(dialog).toHaveCount(0); await expect(trigger).toBeFocused();
  }
});
