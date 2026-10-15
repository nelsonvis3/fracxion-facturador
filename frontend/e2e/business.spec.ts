import type { Page } from "@playwright/test";
import { artifactPath, expect, test } from "./fixtures";
import { readFileSync } from "node:fs";

const tenant = "00000000-0000-4000-8000-000000000001";
const base = `/dashboard/${tenant}`;
const password = "SyntheticE2EPassword2026!";

async function login(page: Page, role = "owner") {
  await page.goto("/");
  await expect(page.locator(".login-intro")).toBeHidden({ timeout: 10000 });
  await page.getByLabel("Correo electrónico", { exact: true }).fill(`${role}@e2e.example`);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("link", { name: "Abrir el espacio de trabajo de Empresa E2E", exact: true })).toBeVisible();
}

test("clientes, catálogo, emisión, pago y reversión con persistencia", async ({ page }) => {
  test.setTimeout(60000);
  const suffix = Date.now();
  const customer = `Cliente E2E ${suffix}`;
  const product = `Servicio E2E ${suffix}`;
  await login(page);
  await page.goto(`${base}/customers`);
  await page.getByRole("button", { name: "Nuevo cliente", exact: true }).click();
  await page.getByLabel("Nombre o denominación *", { exact: true }).fill(customer);
  await page.getByLabel("Provincia / estado", { exact: true }).selectOption({ label: "Formosa" });
  await page.getByLabel("Código postal", { exact: false }).fill("3600");
  await page.getByRole("button", { name: "Crear cliente", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText(customer, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: `Editar ${customer}`, exact: true }).click();
  await page.getByLabel("Correo electrónico", { exact: true }).fill("customer@e2e.example");
  await page.getByRole("button", { name: "Guardar cambios", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("row").filter({ hasText: customer }).getByText("customer@e2e.example", { exact: true })).toBeVisible();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: `Desactivar ${customer}`, exact: true }).click();
  await expect(page.getByText(customer, { exact: true })).toHaveCount(0);
  await page.getByLabel("Filtrar por estado").selectOption("inactive");
  await page.getByRole("row").filter({ hasText: customer }).getByRole("button", { name: "Reactivar" }).click();
  await page.getByLabel("Filtrar por estado").selectOption("active");
  await expect(page.getByText(customer, { exact: true })).toBeVisible();

  await page.goto(`${base}/products`);
  await page.getByRole("button", { name: "Nuevo producto" }).click();
  await page.getByLabel("Nombre *", { exact: true }).fill(product);
  await page.getByLabel("Precio unitario *", { exact: true }).fill("100.00");
  await page.getByRole("combobox", { name: "Tipo", exact: true }).selectOption("service");
  await page.getByRole("button", { name: "Guardar producto" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("row").filter({ hasText: product }).getByRole("cell").first()).toContainText(product);

  await page.goto(`${base}/invoices/new`);
  await page.getByLabel("Buscar cliente", { exact: true }).fill(customer);
  await page.getByLabel("Cliente", { exact: true }).selectOption({ label: customer });
  await page.getByLabel("Buscar producto", { exact: true }).fill(product);
  await page.getByLabel("Producto", { exact: true }).selectOption({ label: `${product} · ARS 100,00` });
  await page.getByRole("button", { name: "Guardar borrador" }).click();
  await expect(page.getByRole("heading", { name: "Borrador", exact: true })).toBeVisible();
  await expect(page.getByText("ARS 121,00", { exact: true }).first()).toBeVisible();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Emitir factura interna", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Interna #/ })).toBeVisible();
  await page.getByRole("button", { name: "Registrar pago", exact: true }).click();
  await page.getByLabel("Importe (ARS) *", { exact: true }).fill("40.00");
  await page.getByRole("dialog").getByRole("button", { name: "Registrar pago", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText("Pagado: ARS 40,00 · Saldo: ARS 81,00", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Pagado: ARS 40,00 · Saldo: ARS 81,00", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Revertir", exact: true }).click();
  await page.getByLabel("Motivo *", { exact: true }).fill("Corrección de prueba");
  await page.getByRole("button", { name: "Confirmar reversión" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText("Pagado: ARS 0,00 · Saldo: ARS 121,00", { exact: true })).toBeVisible();
  await expect(page.getByText("Revertido", { exact: true })).toBeVisible();
  await page.screenshot({ path: artifactPath("invoice.png"), fullPage: true });
  await page.goto(`${base}/audit`);
  await page.getByLabel("Acción de auditoría").selectOption("payment");
  await expect(page.getByRole("cell", { name: "billing.payment_reversal", exact: false }).first()).toBeVisible();
});

test("viewer consulta sin acciones de escritura y no accede a otra empresa", async ({ page }) => {
  await login(page, "viewer");
  await page.goto(`${base}/customers`);
  await expect(page.getByRole("button", { name: "Nuevo cliente", exact: true })).toBeDisabled();
  await page.goto(`${base}/products`);
  await expect(page.getByRole("heading", { name: "Productos y servicios", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Nuevo producto" })).toHaveCount(0);
  await page.goto(`${base}/invoices`);
  await expect(page.getByRole("link", { name: "Nuevo borrador" })).toHaveCount(0);
  await page.goto(`${base}/audit`);
  await expect(page.locator(".notice-error")).toContainText("propietarios y administradores");
  await page.goto("/dashboard/00000000-0000-4000-8000-000000000002/customers");
  await expect(page.locator(".notice-error")).toContainText("no está disponible");
});

test("sesión vencida devuelve al login", async ({ page, context }) => {
  await login(page);
  await context.clearCookies();
  // The application's deliberate location.replace can cancel a navigation
  // waiting for "load"; observe the committed page, then assert the redirect.
  await page.goto(`${base}/payments`, { waitUntil: "commit" });
  await expect(page).toHaveURL("http://127.0.0.1:3010/");
});

test("recuperación genérica y restablecimiento real con token de un solo uso", async ({ page }) => {
  await page.goto("/forgot-password");
  await page.getByLabel("Correo electrónico", { exact: true }).fill("unknown@e2e.example");
  await page.getByRole("button", { name: "Enviar instrucciones" }).click();
  await expect(page.getByRole("status")).toContainText("Si existe una cuenta activa");
  const { uid, token } = JSON.parse(readFileSync("e2e/reset-fixture.json", "utf8")) as { uid: string; token: string };
  const [navigation] = await Promise.all([
    page.waitForRequest(request => request.isNavigationRequest() && new URL(request.url()).pathname === "/reset-password"),
    page.goto(`/reset-password#uid=${encodeURIComponent(uid)}&token=${encodeURIComponent(token)}`),
  ]);
  expect(navigation.url()).not.toContain("token=");
  await page.getByLabel("Nueva contraseña", { exact: true }).fill("NewSyntheticPassword2026!");
  await page.getByLabel("Confirmá la contraseña", { exact: true }).fill("NewSyntheticPassword2026!");
  await page.getByRole("button", { name: "Restablecer contraseña", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("correctamente");
  await page.goto(`/reset-password?uid=${encodeURIComponent(uid)}&token=${encodeURIComponent(token)}`);
  await page.getByLabel("Nueva contraseña", { exact: true }).fill("AnotherSyntheticPassword2026!");
  await page.getByLabel("Confirmá la contraseña", { exact: true }).fill("AnotherSyntheticPassword2026!");
  await page.getByRole("button", { name: "Restablecer contraseña", exact: true }).click();
  await expect(page.locator(".notice-error")).toContainText("no es válido o ha vencido");
});

test("navegación móvil sin desbordamiento horizontal", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto(`${base}/products`);
  await expect(page.getByRole("heading", { name: "Productos y servicios", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("registro público crea empresa, valida errores y permite volver a iniciar sesión", async ({ page }) => {
  const suffix = Date.now();
  const email = `signup.${suffix}@e2e.example`;
  const company = `Empresa registro ${suffix}`;
  const signupPassword = "SyntheticSignupPassword2026!";
  const registrationForm = page.getByRole("form", { name: "Crear una cuenta" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("link", { name: "Crear cuenta", exact: true }).click();
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.getByRole("heading", { name: "Creá tu cuenta" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: artifactPath("facturador-registration-mobile.png"), fullPage: true });
  await registrationForm.getByLabel("Nombre", { exact: true }).fill("Ada");
  await registrationForm.getByLabel("Apellido (opcional)", { exact: true }).fill("Lovelace");
  await registrationForm.getByLabel("Nombre de tu empresa", { exact: true }).fill(company);
  await registrationForm.getByLabel("Correo electrónico", { exact: true }).fill(email);
  await registrationForm.getByLabel("Contraseña", { exact: true }).fill("password123");
  await registrationForm.getByLabel("Confirmá la contraseña", { exact: true }).fill("password123");
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(page.locator("#register-password-error")).toBeVisible();
  await registrationForm.getByLabel("Contraseña", { exact: true }).fill(signupPassword);
  await registrationForm.getByLabel("Confirmá la contraseña", { exact: true }).fill("DifferentSignupPassword2026!");
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(page.locator("#register-password_confirm-error")).toHaveText("Las contraseñas no coinciden.");
  await registrationForm.getByLabel("Confirmá la contraseña", { exact: true }).fill(signupPassword);
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard\/[0-9a-f-]{36}$/);
  const workspace = new URL(page.url()).pathname;
  await expect(page.locator(".business-company")).toContainText(company);
  await expect(page.locator(".business-company")).toContainText("Propietario");
  await page.goto(`${workspace}/customers`);
  await page.getByRole("button", { name: "Nuevo cliente", exact: true }).click();
  await page.getByRole("dialog").getByLabel("Nombre o denominación *", { exact: true }).fill("Cliente del nuevo propietario");
  await page.getByRole("button", { name: "Crear cliente", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText("Cliente del nuevo propietario", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cerrar sesión", exact: true }).click();
  await expect(page).toHaveURL("http://127.0.0.1:3010/");
  await page.getByRole("link", { name: "Crear cuenta", exact: true }).click();
  await registrationForm.getByLabel("Nombre", { exact: true }).fill("Otra cuenta");
  await registrationForm.getByLabel("Nombre de tu empresa", { exact: true }).fill("No debe crearse");
  await registrationForm.getByLabel("Correo electrónico", { exact: true }).fill(email);
  await registrationForm.getByLabel("Contraseña", { exact: true }).fill(signupPassword);
  await registrationForm.getByLabel("Confirmá la contraseña", { exact: true }).fill(signupPassword);
  await page.getByRole("button", { name: "Crear cuenta", exact: true }).click();
  await expect(page.locator("#register-email-error")).toContainText("ya tiene una cuenta");
  await page.getByRole("link", { name: "Ya tengo una cuenta · Iniciar sesión", exact: true }).click();
  await page.locator(".login-form").getByLabel("Correo electrónico", { exact: true }).fill(email);
  await page.locator(".login-form").getByLabel("Contraseña", { exact: true }).fill(signupPassword);
  await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto(`${workspace}/customers`);
  await expect(page.getByText("Cliente del nuevo propietario", { exact: true })).toBeVisible();
  await page.goto(`${base}/customers`);
  await expect(page.locator(".notice-error")).toContainText("no está disponible");
});
